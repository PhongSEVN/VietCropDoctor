"""
Prometheus custom metrics for the Vision-AI service.

Imported by main.py and recorded after each /predict call.
"""
from prometheus_client import Counter, Gauge, Histogram

predictions_total = Counter(
    "predictions_total",
    "Total disease predictions made",
    ["disease", "severity", "crop_type"],
)

ensemble_predictions_total = Counter(
    "ensemble_predictions_total",
    "Per-model prediction count within the ensemble (one increment per model per request)",
    ["model"],
)

prediction_latency = Histogram(
    "prediction_latency_seconds",
    "End-to-end inference time per prediction",
    buckets=[0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
)

model_confidence = Gauge(
    "model_confidence_last",
    "Confidence of the most recent prediction for each disease class",
    ["disease"],
)
