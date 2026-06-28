"""
Multi-model ensemble classifier with weighted soft-voting.

Supports three model families behind a common ``_ModelWrapper`` interface:
  • torchvision CNNs  — EfficientNet-B0, MobileNetV3-Large, ResNet50
  • Vision Transformer — HuggingFace ViTModel head (transformers)
  • YOLO classifier    — Ultralytics YOLOv8-cls (.pt)

Each wrapper returns a per-class probability vector ordered by *its own*
``class_names``. The ensemble reindexes every model to a single canonical class
order before averaging, so models trained with different label orderings still
combine correctly. Models are loaded once at startup and run in parallel via a
ThreadPoolExecutor; the final prediction is the weighted average of softmax
probabilities.
"""
from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms as T
from PIL import Image

from app.config import FALLBACK_CLASSES

logger = logging.getLogger(__name__)

_NORMALIZE_MEAN = [0.485, 0.456, 0.406]
_NORMALIZE_STD = [0.229, 0.224, 0.225]


# Data classes

@dataclass
class ModelConfig:
    name: str
    checkpoint_path: str
    weight: float = 1.0
    input_size: int = 224
    kind: str = "torch"          # "torch" | "yolo"
    arch: Optional[str] = None   # override for checkpoint 'backbone' field


@dataclass
class EnsemblePrediction:
    disease: str
    confidence: float
    top3: list[dict]
    per_model_predictions: list[dict]
    agreement_score: float
    energy: Optional[float] = None   # -logsumexp of mean logits (OOD signal)


# Wrappers

class _ModelWrapper:
    """Common interface: expose ``class_names`` and produce a probability vector."""

    name: str
    class_names: list[str]

    def predict_probs(self, image_bytes: bytes) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def infer(self, image_bytes: bytes) -> tuple[np.ndarray, Optional[np.ndarray]]:
        """Return (softmax_probs, logits_or_None). Default exposes no logits."""
        return self.predict_probs(image_bytes), None


def _build_transform(input_size: int) -> T.Compose:
    return T.Compose([
        T.Resize((input_size, input_size)),
        T.ToTensor(),
        T.Normalize(_NORMALIZE_MEAN, _NORMALIZE_STD),
    ])


class _TorchWrapper(_ModelWrapper):
    """torchvision CNN or ViT loaded from a training checkpoint."""

    def __init__(self, cfg: ModelConfig, device: torch.device) -> None:
        from app.cv.architectures import build_architecture

        self.name = cfg.name
        self._device = device

        ckpt = torch.load(cfg.checkpoint_path, map_location="cpu", weights_only=False)
        if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
            state_dict = ckpt["model_state_dict"]
            num_classes = ckpt.get("num_classes", len(FALLBACK_CLASSES))
            class_names = ckpt.get("class_names") or list(FALLBACK_CLASSES)
            arch = cfg.arch or ckpt.get("backbone") or cfg.name
        else:
            state_dict = ckpt
            num_classes = len(FALLBACK_CLASSES)
            class_names = list(FALLBACK_CLASSES)
            arch = cfg.arch or cfg.name

        model = build_architecture(arch, num_classes)
        model.load_state_dict(state_dict)  # strict — surfaces any arch mismatch
        model.eval().to(device)

        self._model = model
        self.class_names = list(class_names)
        self._transform = _build_transform(cfg.input_size)

    @property
    def model(self) -> nn.Module:
        return self._model

    def infer(self, image_bytes: bytes) -> tuple[np.ndarray, Optional[np.ndarray]]:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = self._transform(img).unsqueeze(0).to(self._device)
        with torch.no_grad():
            logits = self._model(tensor)
            probs = torch.softmax(logits, dim=1)[0].cpu().numpy()
            logits_np = logits[0].cpu().numpy()
        return probs, logits_np

    def predict_probs(self, image_bytes: bytes) -> np.ndarray:
        return self.infer(image_bytes)[0]


class _YoloWrapper(_ModelWrapper):
    """Ultralytics YOLOv8-cls classifier."""

    def __init__(self, cfg: ModelConfig, device: torch.device) -> None:
        from ultralytics import YOLO

        self.name = cfg.name
        self._device = device
        self._model = YOLO(cfg.checkpoint_path)
        names = self._model.names  # {idx: class_name}
        self.class_names = [names[i] for i in range(len(names))]
        self._imgsz = cfg.input_size

    def predict_probs(self, image_bytes: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        result = self._model.predict(
            img, imgsz=self._imgsz, device=self._device, verbose=False
        )[0]
        return result.probs.data.cpu().numpy()


def _make_wrapper(cfg: ModelConfig, device: torch.device) -> _ModelWrapper:
    if cfg.kind == "yolo":
        return _YoloWrapper(cfg, device)
    return _TorchWrapper(cfg, device)


# Classifier

class EnsembleClassifier:
    def __init__(self, configs: list[ModelConfig], device: str = "cpu") -> None:
        self._device = torch.device(device)
        self._configs = configs
        self._wrappers: list[_ModelWrapper] = []
        self.weights: list[float] = []
        self.class_names: list[str] = []

        for cfg in configs:
            try:
                wrapper = _make_wrapper(cfg, self._device)
                self._wrappers.append(wrapper)
                self.weights.append(cfg.weight)
                if not self.class_names:
                    # Canonical class order = first successfully loaded model.
                    self.class_names = wrapper.class_names
                logger.info("Ensemble: loaded '%s' (%s) from %s",
                            cfg.name, cfg.kind, cfg.checkpoint_path)
            except Exception as exc:
                logger.warning("Ensemble: skipping '%s' — %s", cfg.name, exc)

        if not self._wrappers:
            raise RuntimeError("EnsembleClassifier: no models could be loaded")

        # Precompute per-model reindex maps onto the canonical class order.
        self._reindex: list[Optional[np.ndarray]] = [
            self._build_reindex(w.class_names) for w in self._wrappers
        ]

        total = sum(self.weights)
        self.weights = [w / total for w in self.weights]
        logger.info("Ensemble ready | models=%d device=%s classes=%d",
                    len(self._wrappers), device, len(self.class_names))

    @property
    def model_count(self) -> int:
        return len(self._wrappers)

    def _build_reindex(self, model_classes: list[str]) -> Optional[np.ndarray]:
        """Return an index array mapping model probs → canonical order, or None
        when the ordering already matches (fast path)."""
        if model_classes == self.class_names:
            return None
        pos = {c: i for i, c in enumerate(model_classes)}
        try:
            return np.array([pos[c] for c in self.class_names], dtype=np.int64)
        except KeyError as exc:
            raise RuntimeError(
                f"Model class set does not cover canonical classes: missing {exc}"
            )

    def _aligned_probs(self, idx: int, probs: np.ndarray) -> np.ndarray:
        remap = self._reindex[idx]
        return probs if remap is None else probs[remap]

    def mc_uncertainty(self, image_bytes: bytes) -> Optional[float]:
        """MC-Dropout uncertainty on the first torch model in the ensemble.

        Runs N stochastic forward passes (dropout active) and returns the
        normalised predictive entropy in [0, 1]. Returns None when no torch model
        is loaded (e.g. a YOLO-only ensemble) or estimation fails.
        """
        from app.cv.uncertainty import estimate_uncertainty

        for w in self._wrappers:
            if isinstance(w, _TorchWrapper):
                try:
                    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                    tensor = w._transform(img).unsqueeze(0).to(self._device)
                    return estimate_uncertainty(w.model, tensor)["uncertainty_score"]
                except Exception as exc:
                    logger.warning("Ensemble MC-dropout uncertainty failed: %s", exc)
                    return None
        return None

    def _energy_from_logits(self, raw_logits: list[Optional[np.ndarray]]) -> Optional[float]:
        """Weighted-mean logits across models that expose them, then energy."""
        from app.cv.ood import energy_score

        items = [(i, lg) for i, lg in enumerate(raw_logits) if lg is not None]
        if not items:
            return None
        w = np.array([self.weights[i] for i, _ in items], dtype=np.float64)
        w /= w.sum()
        mean_logits = np.average(np.stack([lg for _, lg in items]), axis=0, weights=w)
        try:
            return energy_score(mean_logits)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Energy score failed: %s", exc)
            return None

    def predict(self, image_bytes: bytes) -> EnsemblePrediction:
        n = len(self._wrappers)
        raw: list[Optional[np.ndarray]] = [None] * n
        raw_logits: list[Optional[np.ndarray]] = [None] * n

        with ThreadPoolExecutor(max_workers=n) as pool:
            future_map = {
                pool.submit(w.infer, image_bytes): i
                for i, w in enumerate(self._wrappers)
            }
            for future in as_completed(future_map):
                i = future_map[future]
                try:
                    probs, logits = future.result()
                    raw[i] = self._aligned_probs(i, probs)
                    if logits is not None:
                        raw_logits[i] = self._aligned_probs(i, logits)
                except Exception as exc:
                    logger.warning("Ensemble model '%s' failed: %s",
                                   self._wrappers[i].name, exc)

        valid = [(i, p) for i, p in enumerate(raw) if p is not None]
        if not valid:
            raise RuntimeError("All ensemble models failed on this image")

        probs_stack = np.stack([p for _, p in valid])                    # (M, C)
        weights_arr = np.array([self.weights[i] for i, _ in valid], dtype=np.float32)
        weights_arr /= weights_arr.sum()                                 # renorm
        avg_probs = np.average(probs_stack, axis=0, weights=weights_arr)

        top_k = min(3, len(self.class_names))
        top_idxs = np.argsort(avg_probs)[::-1][:top_k].tolist()
        top3 = [
            {"class_name": self.class_names[i], "confidence": round(float(avg_probs[i]), 4)}
            for i in top_idxs
        ]
        disease = top3[0]["class_name"]
        confidence = top3[0]["confidence"]
        top1_idx = top_idxs[0]

        agreement_score = round(
            sum(1 for _, p in valid if int(np.argmax(p)) == top1_idx) / len(valid), 4
        )

        per_model_predictions = [
            {
                "name": self._wrappers[i].name,
                "disease": self.class_names[int(np.argmax(p))],
                "confidence": round(float(np.max(p)), 4),
            }
            for i, p in valid
        ]

        return EnsemblePrediction(
            disease=disease,
            confidence=confidence,
            top3=top3,
            per_model_predictions=per_model_predictions,
            agreement_score=agreement_score,
            energy=self._energy_from_logits(raw_logits),
        )
