"""
MLflow experiment tracking helpers.

Metrics logged per training run:
  - test_macro_f1  (used as ensemble weight — fair on the imbalanced dataset)
  - test_weighted_f1
  - test_acc
  - val_acc / val_loss (per epoch)
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import mlflow


TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT", "plant-disease-classification")


def get_client() -> mlflow.MlflowClient:
    mlflow.set_tracking_uri(TRACKING_URI)
    return mlflow.MlflowClient()


@contextmanager
def start_run(model_name: str, tags: dict[str, str] | None = None):
    """Context manager that wraps mlflow.start_run with standard tagging."""
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(run_name=model_name, tags=tags or {}) as run:
        mlflow.set_tag("model_name", model_name)
        yield run


def log_metrics(metrics: dict[str, float]) -> None:
    """Log a flat dict of metric name → value to the active MLflow run."""
    mlflow.log_metrics(metrics)


def log_model_artifact(checkpoint_path: str | Path, artifact_path: str = "model") -> None:
    """Log a model checkpoint file as an MLflow artifact."""
    mlflow.log_artifact(str(checkpoint_path), artifact_path=artifact_path)


def get_best_weights(experiment_name: str = EXPERIMENT_NAME) -> dict[str, float]:
    """Return {model_name: score} for the latest run of each model.

    The score is the test **macro-F1** — the fair metric on this imbalanced dataset,
    so weighted voting favours models that handle minority classes well rather than
    those that merely score high overall accuracy. Falls back to test_acc, then the
    last logged val_acc, for older runs that predate macro-F1 logging.
    """
    client = get_client()
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        return {}

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        order_by=["start_time DESC"],
    )

    weights: dict[str, float] = {}
    for run in runs:
        name = run.data.tags.get("model_name")
        metrics = run.data.metrics
        score = (
            metrics.get("test_macro_f1")
            or metrics.get("test_acc")
            or metrics.get("val_acc")
        )
        if name and score and name not in weights:
            weights[name] = score

    return weights
