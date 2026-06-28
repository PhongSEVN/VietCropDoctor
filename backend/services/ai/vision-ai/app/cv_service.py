"""
CV inference service — loads model checkpoint and runs prediction.

predict() is synchronous and intended to be called via asyncio.to_thread
from the FastAPI endpoint so it does not block the event loop.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

import torch
import torchvision.transforms as T
from PIL import Image

from app.config import (
    CKPT_PATH,
    ENSEMBLE_CONFIGS,
    ENSEMBLE_ENABLED,
    FALLBACK_CLASSES,
    OOD_GATE_ENABLED,
    OOD_GATE_PATH,
    OOD_THRESHOLD,
)
from app.state import app_state

logger = logging.getLogger(__name__)

_OOD_MESSAGE = (
    "Ảnh không giống lá cây trồng (cà phê, lúa, mía, ngô). "
    "Vui lòng chụp lại lá cây cận cảnh, rõ nét, đủ ánh sáng."
)

_IMAGE_SIZE = 224
_NORMALIZE_MEAN = [0.485, 0.456, 0.406]
_NORMALIZE_STD  = [0.229, 0.224, 0.225]

_DEFAULT_TRANSFORM = T.Compose([
    T.Resize((_IMAGE_SIZE, _IMAGE_SIZE)),
    T.ToTensor(),
    T.Normalize(_NORMALIZE_MEAN, _NORMALIZE_STD),
])


def _detect_num_classes(state_dict: dict) -> int:
    for key in ("backbone.classifier.3.1.weight",
                "backbone.fc.1.weight",
                "classifier.1.weight"):
        if key in state_dict:
            return state_dict[key].shape[0]
    for k, v in state_dict.items():
        if "weight" in k and v.ndim == 2:
            return v.shape[0]
    return len(FALLBACK_CLASSES)


def _detect_arch(state_dict: dict) -> str:
    """Infer the architecture name from checkpoint state-dict key prefixes."""
    keys = list(state_dict.keys())
    if any(k.startswith("backbone.features") or k.startswith("backbone.classifier") for k in keys):
        return "mobilenetv3"
    if any(k.startswith(("backbone.layer", "backbone.conv1", "backbone.fc")) for k in keys):
        return "resnet50"
    if any("backbone.embeddings" in k or "backbone.encoder.layer" in k for k in keys):
        return "vit"
    return "efficientnet_b0"


def _load_model(state_dict: dict, num_classes: int, arch: Optional[str] = None):
    """Build the serving architecture and load weights (strict).

    Uses app.cv.architectures.build_architecture — the same head-matched builders
    as the ensemble — so no dependency on any legacy cv/<arch>/model.py package.
    """
    from app.cv.architectures import build_architecture

    model = build_architecture(arch or _detect_arch(state_dict), num_classes)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def _build_explanation(disease: str, confidence: float) -> str:
    if confidence == 0.0:
        return "Mô hình đang chạy ở chế độ demo — không có checkpoint."
    level = (
        "cao"   if confidence >= 0.8 else
        "vừa"   if confidence >= 0.5 else
        "thấp"
    )
    return (
        f"Độ tin cậy chẩn đoán {level} ({confidence * 100:.1f}%). "
        "Kết quả mang tính tham khảo, nên xác nhận thêm với chuyên gia."
    )


_SEVERITY_ADVICE = {
    "healthy":  "Cây trồng đang phát triển tốt. Tiếp tục chăm sóc định kỳ và theo dõi sức khỏe cây.",
    "mild":     "Phát hiện dấu hiệu bệnh nhẹ. Theo dõi sát trong 3–5 ngày tới và cân nhắc biện pháp phòng ngừa.",
    "moderate": "Bệnh đang ở mức trung bình. Nên áp dụng thuốc bảo vệ thực vật phù hợp và tham khảo kỹ sư nông nghiệp.",
    "severe":   "Bệnh nặng — cần xử lý khẩn cấp. Liên hệ ngay kỹ sư nông nghiệp địa phương để được tư vấn.",
}


def _compute_severity(disease: str, confidence: float) -> tuple[str, float, str]:
    if "healthy" in disease.lower():
        return "healthy", 0.0, _SEVERITY_ADVICE["healthy"]
    if confidence >= 0.80:
        sev, score = "severe",   min(0.7 + (confidence - 0.80) * 1.5, 1.0)
    elif confidence >= 0.60:
        sev, score = "moderate", 0.4 + (confidence - 0.60) * 1.5
    else:
        sev, score = "mild",     confidence * 0.67
    return sev, round(score, 4), _SEVERITY_ADVICE[sev]


# Public

def _load_ensemble() -> None:
    """Create an EnsembleClassifier from ENSEMBLE_CONFIGS and store in app_state."""
    from app.cv.ensemble import EnsembleClassifier, ModelConfig

    device = "cuda" if torch.cuda.is_available() else "cpu"
    configs = [
        ModelConfig(
            name=c["name"],
            checkpoint_path=c["path"],
            weight=c["weight"],
            input_size=c["input_size"],
            kind=c.get("kind", "torch"),
            arch=c.get("arch"),
        )
        for c in ENSEMBLE_CONFIGS
    ]

    # Override voting weights with MLflow-recorded test macro-F1 (the documented
    # scheme) — replaces YOLO's top-1 proxy with its real macro-F1. Best-effort:
    # falls back to the config weights when MLflow is unavailable.
    try:
        from app import model_sync
        f1_weights = model_sync.fetch_macro_f1_weights()
        for cfg in configs:
            if cfg.name in f1_weights:
                cfg.weight = f1_weights[cfg.name]
    except Exception as exc:
        logger.warning("MLflow macro-F1 weight override skipped: %s", exc)

    try:
        ensemble = EnsembleClassifier(configs, device=device)
        app_state.ensemble = ensemble
        app_state.class_names = ensemble.class_names
        app_state.model_loaded = True
    except Exception as exc:
        logger.error("Ensemble load failed: %s — running in mock mode", exc)


def _load_ood_gate() -> None:
    """Load the OOD gate (fitted artifact or heuristic default) into app_state."""
    if not OOD_GATE_ENABLED:
        app_state.ood_gate = None
        return
    from app.cv.ood import OODGate
    app_state.ood_gate = OODGate.load(OOD_GATE_PATH, threshold=OOD_THRESHOLD)


def _apply_ood_gate(result: dict, ep, uncertainty) -> None:
    """Run the OOD gate on the ensemble signals and flag irrelevant images."""
    result["is_in_distribution"] = True
    result["ood_message"] = None
    result["ood_score"] = None

    gate = app_state.ood_gate
    if gate is None:
        return
    in_dist, p_in = gate.decide({
        "energy": ep.energy,
        "agreement": ep.agreement_score,
        "mc_uncertainty": uncertainty,
    })
    result["is_in_distribution"] = in_dist
    result["ood_score"] = p_in
    if not in_dist:
        result["ood_message"] = _OOD_MESSAGE
        result["explanation"] = _OOD_MESSAGE


def load_cv_model() -> None:
    """Load CV model (or ensemble) into app_state. Called once at startup."""
    app_state.transform = _DEFAULT_TRANSFORM
    app_state.class_names = list(FALLBACK_CLASSES)
    _load_ood_gate()

    if ENSEMBLE_ENABLED:
        logger.info("Ensemble mode enabled — loading %d checkpoints", len(ENSEMBLE_CONFIGS))
        _load_ensemble()
        return

    if not CKPT_PATH.exists():
        logger.warning("Checkpoint not found at %s — running in mock mode", CKPT_PATH)
        return

    try:
        ckpt = torch.load(CKPT_PATH, map_location="cpu", weights_only=False)

        if "model_state_dict" in ckpt:
            num_classes = ckpt.get("num_classes", len(FALLBACK_CLASSES))
            class_names = ckpt.get("class_names") or list(FALLBACK_CLASSES)
            state_dict  = ckpt["model_state_dict"]
        else:
            state_dict  = ckpt
            num_classes = _detect_num_classes(state_dict)
            class_names = sorted(FALLBACK_CLASSES)[:num_classes]

        arch = ckpt.get("backbone") if isinstance(ckpt, dict) and "model_state_dict" in ckpt else None
        model = _load_model(state_dict, num_classes, arch)

        app_state.model = model
        app_state.class_names = class_names
        app_state.model_loaded = True
        logger.info(
            "CV model loaded | classes=%d checkpoint=%s",
            num_classes, CKPT_PATH.name,
        )
    except Exception as exc:
        logger.error("CV model load failed: %s", exc)


def predict(image_bytes: bytes) -> dict:
    """Run inference on raw image bytes.

    Returns a dict compatible with PredictResult. When ensemble_enabled the
    ensemble path is used; otherwise the single-model path runs.
    """
    # Mock path (no model loaded)
    if not app_state.model_loaded:
        disease = app_state.class_names[0] if app_state.class_names else "unknown"
        severity, severity_score, severity_advice = _compute_severity(disease, 0.0)
        return {
            "disease":         disease,
            "confidence":      0.0,
            "top3":            [{"class_name": c, "confidence": 0.0} for c in app_state.class_names[:3]],
            "explanation":     _build_explanation("", 0.0),
            "severity":        severity,
            "severity_score":  severity_score,
            "severity_advice": severity_advice,
            "agreement_score": 1.0,
            "ensemble_used":   False,
            "model_count":     0,
        }

    # Ensemble path
    if app_state.ensemble is not None:
        ep = app_state.ensemble.predict(image_bytes)
        severity, severity_score, severity_advice = _compute_severity(ep.disease, ep.confidence)
        result: dict = {
            "disease":         ep.disease,
            "confidence":      ep.confidence,
            "top3":            ep.top3,
            "explanation":     _build_explanation(ep.disease, ep.confidence),
            "severity":        severity,
            "severity_score":  severity_score,
            "severity_advice": severity_advice,
            "agreement_score": ep.agreement_score,
            "ensemble_used":   True,
            "model_count":     app_state.ensemble.model_count,
            # Internal-only (filtered out of the HTTP response by PredictResult);
            # consumed by main.py to record ensemble_predictions_total per model.
            "per_model_predictions": ep.per_model_predictions,
        }

        # MC Dropout uncertainty on the ensemble's first torch model (normalised
        # predictive entropy). Complements the agreement_score signal. Returns
        # None only if no torch model is loaded or estimation fails.
        uncertainty = app_state.ensemble.mc_uncertainty(image_bytes)
        result["uncertainty_score"] = uncertainty

        # OOD gate — flag images that are not crop leaves (energy + agreement +
        # uncertainty). Keeps the top-1 result but marks is_in_distribution=False.
        _apply_ood_gate(result, ep, uncertainty)

        return result

    # Single-model path
    img    = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    tensor = app_state.transform(img).unsqueeze(0)

    with torch.no_grad():
        logits = app_state.model(tensor)
        probs  = torch.softmax(logits, dim=1)[0]

    top_k   = min(3, len(app_state.class_names))
    top_idx = probs.topk(top_k).indices.tolist()
    top3 = [
        {"class_name": app_state.class_names[i], "confidence": round(probs[i].item(), 4)}
        for i in top_idx
    ]
    disease    = top3[0]["class_name"]
    confidence = top3[0]["confidence"]
    severity, severity_score, severity_advice = _compute_severity(disease, confidence)

    result = {
        "disease":         disease,
        "confidence":      confidence,
        "top3":            top3,
        "explanation":     _build_explanation(disease, confidence),
        "severity":        severity,
        "severity_score":  severity_score,
        "severity_advice": severity_advice,
        "agreement_score": 1.0,
        "ensemble_used":   False,
        "model_count":     1,
    }

    # MC Dropout uncertainty
    try:
        from app.cv.uncertainty import estimate_uncertainty
        unc = estimate_uncertainty(app_state.model, tensor)
        result["uncertainty_score"] = unc.get("uncertainty_score")
    except Exception as exc:
        logger.debug("Uncertainty estimation failed: %s", exc)

    return result
