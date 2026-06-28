"""
Out-Of-Distribution (OOD) gate for the disease classifier.

The 25-class softmax always sums to 1, so the ensemble is forced to assign *some*
disease to *any* image — including a cat, a selfie, or a leaf outside the 25
classes. This gate sits after the ensemble and decides whether the image is
actually in-distribution (a coffee/rice/sugarcane/maize leaf) using three signals
that are free by-products of the existing 5-model ensemble:

  • energy        — -logsumexp of the (weighted) mean ensemble logits. Unlike
                    softmax it is NOT normalised, so a "nothing stands out" image
                    yields a high energy → likely OOD.
  • agreement     — fraction of models that agree on the top-1 class (already
                    computed by the ensemble). Low agreement → likely OOD.
  • mc_uncertainty— normalised predictive entropy from MC-Dropout. High → OOD.

The three signals are combined by a tiny logistic regression whose parameters are
loaded from an artifact (cv/results/ood_gate.json, produced offline by
scripts/fit_ood_gate.py). When the artifact is absent the gate falls back to a
well-scaled heuristic on agreement + uncertainty (energy needs calibration, so it
is only used once a fitted gate provides its standardisation).

Reference: Liu et al., "Energy-based Out-of-distribution Detection", NeurIPS 2020.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("vision_ai.ood")

# Feature order is fixed and shared with the fitting script's artifact.
FEATURES = ("energy", "agreement", "mc_uncertainty")


def energy_score(logits, temperature: float = 1.0) -> float:
    """Energy = -T * logsumexp(logits / T). Higher energy ⇒ more out-of-distribution."""
    z = np.asarray(logits, dtype=np.float64) / temperature
    m = float(np.max(z))
    lse = m + math.log(float(np.sum(np.exp(z - m))))
    return float(-temperature * lse)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class OODGate:
    """Decides in-distribution vs OOD from the ensemble signals."""

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        coef: Optional[list[float]] = None,
        intercept: float = 0.0,
        mean: Optional[dict[str, float]] = None,
        std: Optional[dict[str, float]] = None,
        feature_order: tuple[str, ...] = FEATURES,
        fitted: bool = False,
    ) -> None:
        self.threshold = threshold
        self.coef = coef
        self.intercept = intercept
        self.mean = mean or {}
        self.std = std or {}
        self.feature_order = tuple(feature_order)
        self.fitted = fitted

    # Construction

    @classmethod
    def default(cls, threshold: float = 0.5) -> "OODGate":
        """Heuristic gate (no fitted artifact)."""
        return cls(threshold=threshold, fitted=False)

    @classmethod
    def load(cls, path, threshold: float = 0.5) -> "OODGate":
        """Load a fitted logistic gate from JSON, or return the heuristic default."""
        p = Path(path)
        if not p.is_file():
            logger.info("OOD gate artifact not found at %s — using heuristic default", p)
            return cls.default(threshold)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            gate = cls(
                threshold=float(d.get("threshold", threshold)),
                coef=[float(c) for c in d["coef"]],
                intercept=float(d.get("intercept", 0.0)),
                mean={k: float(v) for k, v in d["mean"].items()},
                std={k: float(v) for k, v in d["std"].items()},
                feature_order=tuple(d.get("feature_order", FEATURES)),
                fitted=True,
            )
            logger.info("OOD gate loaded (fitted) from %s | threshold=%.3f", p, gate.threshold)
            return gate
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load OOD gate (%s) — heuristic default", exc)
            return cls.default(threshold)

    # Decision

    def _heuristic_prob(self, signals: dict) -> float:
        """In-distribution probability from agreement (+ uncertainty when present).

        Both inputs are well-scaled in [0, 1]; energy is intentionally NOT used here
        because its scale is uncalibrated until a fitted gate provides mean/std.
        """
        agree = float(signals.get("agreement") or 0.0)
        unc = signals.get("mc_uncertainty")
        if unc is None:
            return agree
        return 0.5 * agree + 0.5 * (1.0 - float(unc))

    def decide(self, signals: dict) -> tuple[bool, float]:
        """Return (is_in_distribution, prob_in_distribution)."""
        if self.fitted and self.coef is not None:
            try:
                z = self.intercept
                for c, feat in zip(self.coef, self.feature_order):
                    v = signals.get(feat)
                    if v is None:
                        raise KeyError(feat)
                    s = self.std.get(feat) or 1.0
                    z += c * ((float(v) - self.mean.get(feat, 0.0)) / s)
                p = _sigmoid(z)
            except Exception:  # noqa: BLE001 — a missing signal falls back gracefully
                p = self._heuristic_prob(signals)
        else:
            p = self._heuristic_prob(signals)

        return (p >= self.threshold), round(float(p), 4)
