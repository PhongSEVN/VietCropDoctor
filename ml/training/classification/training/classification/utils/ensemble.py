"""Ensemble weighted soft-voting + leave-one-out analysis.

Model-agnostic: works on per-model softmax probability arrays, so the backend
vision-ai ensemble and any offline evaluation can share the same logic.

Two ablation knobs from the reference projects live here:
  - the voting weights can come from val_accuracy OR val_macro_f1 (macro-F1 is
    the fairer choice on an imbalanced dataset);
  - leave_one_out() quantifies how much each model contributes to the ensemble.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import f1_score

VALID_WEIGHT_METRICS = ("val_accuracy", "val_macro_f1", "uniform")


def normalize_weights(weights) -> np.ndarray:
    """Return weights scaled to sum to 1. Raises if the sum is not positive."""
    w = np.asarray(weights, dtype=float)
    total = w.sum()
    if total <= 0:
        raise ValueError("Sum of weights must be positive.")
    return w / total


def select_weights(model_scores: dict, metric: str = "val_accuracy") -> tuple[list[str], np.ndarray]:
    """Build voting weights from per-model validation scores.

    Args:
        model_scores: ``{model_name: {"val_accuracy": .., "val_macro_f1": ..}}``.
        metric: one of VALID_WEIGHT_METRICS. "uniform" weights every model equally.

    Returns:
        (names, weights) with names and weights aligned and weights summing to 1.
    """
    if metric not in VALID_WEIGHT_METRICS:
        raise ValueError(f"metric must be one of {VALID_WEIGHT_METRICS}, got {metric!r}")
    names = list(model_scores.keys())
    if metric == "uniform":
        raw = [1.0 for _ in names]
    else:
        raw = [float(model_scores[name][metric]) for name in names]
    return names, normalize_weights(raw)


def weighted_vote(model_probs, weights) -> np.ndarray:
    """Soft voting over per-model probabilities.

    Args:
        model_probs: array-like (M, N, C) — M models, N samples, C classes.
        weights: (M,) voting weights (need not be normalised).

    Returns:
        Predicted class indices (N,).
    """
    probs = np.asarray(model_probs, dtype=float)
    if probs.ndim != 3:
        raise ValueError(f"model_probs must be (M, N, C); got shape {probs.shape}")
    w = normalize_weights(weights).reshape(-1, 1, 1)
    combined = (probs * w).sum(axis=0)
    return combined.argmax(axis=1)


def ensemble_macro_f1(model_probs, weights, y_true) -> float:
    """Macro-F1 of the weighted soft-voting ensemble."""
    preds = weighted_vote(model_probs, weights)
    return float(f1_score(y_true, preds, average="macro", zero_division=0))


def leave_one_out(model_probs, weights, y_true, names: list[str]) -> dict:
    """Macro-F1 of the full ensemble and of each leave-one-out subset.

    Returns ``{"all": f1, "drop:<name>": f1, ...}`` so a smaller number for
    "drop:<name>" means that model contributed more to the ensemble.
    """
    probs = np.asarray(model_probs, dtype=float)
    w = np.asarray(weights, dtype=float)
    result = {"all": ensemble_macro_f1(probs, w, y_true)}
    if len(names) <= 1:
        return result
    for i, name in enumerate(names):
        keep = [j for j in range(len(names)) if j != i]
        result[f"drop:{name}"] = ensemble_macro_f1(probs[keep], w[keep], y_true)
    return result
