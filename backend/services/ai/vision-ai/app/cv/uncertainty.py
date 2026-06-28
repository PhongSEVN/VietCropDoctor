"""
Uncertainty estimation via Monte Carlo (MC) Dropout.

The model is run N times with dropout layers active (train mode) during
inference. Variance across runs reflects epistemic uncertainty.

uncertainty_score: 0.0 = confident, 1.0 = maximally uncertain.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import torch

logger = logging.getLogger("vision_ai.uncertainty")

_MC_SAMPLES = 5          # number of stochastic forward passes
_MIN_SAMPLES_FOR_STD = 2  # minimum runs before std is meaningful


def _enable_dropout(model: torch.nn.Module) -> None:
    """Set all Dropout layers to training mode while keeping BN in eval mode."""
    for m in model.modules():
        if isinstance(m, (torch.nn.Dropout, torch.nn.Dropout2d)):
            m.train()


def estimate_uncertainty(
    model: torch.nn.Module,
    tensor: torch.Tensor,
    n_samples: int = _MC_SAMPLES,
) -> dict:
    """Run MC Dropout and return mean prediction + uncertainty score.

    Args:
        model: The loaded classification model (must have Dropout layers).
        tensor: Preprocessed image tensor of shape [1, C, H, W].
        n_samples: Number of Monte Carlo forward passes.

    Returns:
        dict with keys:
          - mean_probs: np.ndarray [num_classes] — averaged softmax probabilities
          - std_probs:  np.ndarray [num_classes] — standard deviation per class
          - uncertainty_score: float in [0, 1]
          - top_class_idx: int — argmax of mean_probs
    """
    model.eval()
    _enable_dropout(model)

    all_probs: list[np.ndarray] = []
    with torch.no_grad():
        for _ in range(n_samples):
            logits = model(tensor)
            probs = torch.softmax(logits, dim=1)[0].cpu().numpy()
            all_probs.append(probs)

    model.eval()  # restore full eval mode (disables dropout again)

    stacked = np.stack(all_probs, axis=0)          # [n_samples, num_classes]
    mean_probs = stacked.mean(axis=0)
    std_probs  = stacked.std(axis=0)

    top_idx = int(mean_probs.argmax())

    # Uncertainty score: normalised entropy of mean probabilities
    # H = -sum(p * log(p)); max entropy = log(num_classes)
    eps = 1e-10
    entropy = -np.sum(mean_probs * np.log(mean_probs + eps))
    max_entropy = np.log(len(mean_probs))
    uncertainty_score = float(entropy / max_entropy) if max_entropy > 0 else 0.0

    return {
        "mean_probs":        mean_probs,
        "std_probs":         std_probs,
        "uncertainty_score": round(uncertainty_score, 4),
        "top_class_idx":     top_idx,
    }
