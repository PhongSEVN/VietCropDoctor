"""
Fit the OOD gate (logistic regression over energy + agreement + MC-Dropout
uncertainty) and report AUROC / FPR@95%TPR for the thesis.

This does NOT retrain any CNN. It runs the existing 5-model ensemble once over a
small set of in-distribution leaf images and a set of out-of-distribution images
(other plants, random objects, blurry/screenshot), collects the three signals,
fits a tiny logistic regression, and writes cv/results/ood_gate.json — which the
service loads at startup.

Run inside the vision-ai service root (so `app` is importable):

    python scripts/fit_ood_gate.py \
        --in-dir  cv/results/_ood_eval/in \
        --ood-dir cv/results/_ood_eval/ood \
        --out     cv/results/ood_gate.json

Requires: torch, transformers, ultralytics, numpy, Pillow (already in the image)
and ENSEMBLE checkpoints present under cv/results/.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Make `app` importable when run from the service root.
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SERVICE_ROOT))

FEATURES = ("energy", "agreement", "mc_uncertainty")
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


# Signal collection

def _build_ensemble():
    import torch
    from app.config import ENSEMBLE_CONFIGS
    from app.cv.ensemble import EnsembleClassifier, ModelConfig

    configs = [
        ModelConfig(
            name=c["name"], checkpoint_path=c["path"], weight=c["weight"],
            input_size=c["input_size"], kind=c.get("kind", "torch"), arch=c.get("arch"),
        )
        for c in ENSEMBLE_CONFIGS
    ]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return EnsembleClassifier(configs, device=device)


def _signals_for_dir(ensemble, directory: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    images = [p for p in directory.rglob("*") if p.suffix.lower() in _IMAGE_EXTS]
    print(f"  {directory}: {len(images)} images")
    for p in images:
        try:
            data = p.read_bytes()
            ep = ensemble.predict(data)
            unc = ensemble.mc_uncertainty(data)
            if ep.energy is None or unc is None:
                continue
            rows.append([float(ep.energy), float(ep.agreement_score), float(unc)])
        except Exception as exc:  # noqa: BLE001
            print(f"    skip {p.name}: {exc}")
    return rows


# Logistic regression + metrics (numpy only)

def _fit_logreg(X: np.ndarray, y: np.ndarray, epochs=4000, lr=0.1, l2=1e-3):
    n, d = X.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(epochs):
        p = 1.0 / (1.0 + np.exp(-(X @ w + b)))
        gw = X.T @ (p - y) / n + l2 * w
        gb = float(np.mean(p - y))
        w -= lr * gw
        b -= lr * gb
    return w, b


def _auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    n_pos = float(labels.sum())
    n_neg = float(len(labels) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    return float((ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _fpr_at_tpr(scores: np.ndarray, labels: np.ndarray, target_tpr=0.95):
    pos = np.sort(scores[labels == 1])
    if len(pos) == 0:
        return float("nan"), 0.5
    k = int(np.floor((1.0 - target_tpr) * len(pos)))
    k = min(max(k, 0), len(pos) - 1)
    thr = float(pos[k])  # keep target_tpr of positives (in-dist) above thr
    neg = scores[labels == 0]
    fpr = float(np.mean(neg >= thr)) if len(neg) else float("nan")
    return fpr, thr


# Main

def main() -> None:
    ap = argparse.ArgumentParser(description="Fit the OOD gate and report AUROC/FPR95")
    ap.add_argument("--in-dir", required=True, help="Folder of in-distribution crop-leaf images")
    ap.add_argument("--ood-dir", required=True, help="Folder of out-of-distribution images")
    ap.add_argument("--out", default="cv/results/ood_gate.json")
    args = ap.parse_args()

    print("Loading ensemble...")
    ensemble = _build_ensemble()

    print("Collecting signals (in-distribution)...")
    pos = _signals_for_dir(ensemble, Path(args.in_dir))
    print("Collecting signals (out-of-distribution)...")
    neg = _signals_for_dir(ensemble, Path(args.ood_dir))

    if not pos or not neg:
        raise SystemExit("Need images in BOTH --in-dir and --ood-dir.")

    X = np.array(pos + neg, dtype=np.float64)
    y = np.array([1] * len(pos) + [0] * len(neg), dtype=np.float64)  # 1 = in-distribution

    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0
    Xs = (X - mean) / std

    w, b = _fit_logreg(Xs, y)
    scores = 1.0 / (1.0 + np.exp(-(Xs @ w + b)))  # P(in-distribution)

    auroc = _auroc(scores, y)
    fpr95, thr = _fpr_at_tpr(scores, y, target_tpr=0.95)

    artifact = {
        "feature_order": list(FEATURES),
        "coef": [float(c) for c in w],
        "intercept": float(b),
        "mean": {f: float(m) for f, m in zip(FEATURES, mean)},
        "std": {f: float(s) for f, s in zip(FEATURES, std)},
        "threshold": float(thr),       # operating point at 95% TPR
        "metrics": {
            "auroc": auroc,
            "fpr_at_95_tpr": fpr95,
            "n_in_distribution": len(pos),
            "n_ood": len(neg),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n OOD gate fitted")
    print(f"  AUROC          : {auroc:.4f}   (1.0 = perfect separation)")
    print(f"  FPR@95%TPR     : {fpr95:.4f}   (lower = fewer junk images pass)")
    print(f"  threshold      : {thr:.4f}")
    print(f"  saved          : {out}")


if __name__ == "__main__":
    main()
