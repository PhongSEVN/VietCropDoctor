"""Pull promoted model weights from MLflow into the local serving directory.

This closes the retrain hot-swap loop. The Airflow `retrain_classifier` DAG
trains, evaluates, and promotes each model to the MLflow Model Registry
(``VietCropDoctor-<name>``, stage ``Production``). Previously the DAG then called
``/admin/reload-model``, but that only re-read files already on disk — so a newly
promoted model never actually reached the service. This module fills that gap:
for every canonical model it resolves the promoted run, downloads its checkpoint
artifact, and writes it to the exact path the ensemble loader reads.

Every operation is best-effort and per-model isolated: any failure is logged and
skipped, never raised, so a reload never crashes the service and the ensemble
keeps serving whatever weights are already on disk.

Vocabulary is canonical and identical across the DAG, the MLflow registry, and
the serving ``cv/results/<name>/`` directory: efficientnet_b0, mobilenetv3,
resnet50, vit, yolo.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger("vision_ai.model_sync")

_SERVICE_ROOT = Path(__file__).parent.parent
_RESULTS_ROOT = _SERVICE_ROOT / "cv" / "results"

_MLFLOW_URI       = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
_EXPERIMENT_NAME  = os.getenv("MLFLOW_EXPERIMENT", "plant-disease-classification")
_SYNC_ENABLED     = os.getenv("MODEL_SYNC_ENABLED", "true").lower() == "true"
_REGISTRY_PREFIX  = "VietCropDoctor-"

# canonical name -> (destination checkpoint path, candidate artifact filenames)
# torch models log a stable artifact at "model/best_model.pth"; YOLO's weights
# are a .pt saved by ultralytics. Candidates are tried in order.
_MODELS: dict[str, tuple[Path, tuple[str, ...]]] = {
    "efficientnet_b0": (_RESULTS_ROOT / "efficientnet_b0" / "models" / "best_model.pth",
                        ("model/best_model.pth",)),
    "mobilenetv3":     (_RESULTS_ROOT / "mobilenetv3" / "models" / "best_model.pth",
                        ("model/best_model.pth",)),
    "resnet50":        (_RESULTS_ROOT / "resnet50" / "models" / "best_model.pth",
                        ("model/best_model.pth",)),
    "vit":             (_RESULTS_ROOT / "vit" / "models" / "best_model.pth",
                        ("model/best_model.pth",)),
    "yolo":            (_RESULTS_ROOT / "yolo" / "models" / "best.pt",
                        ("model/best.pt", "weights/best.pt", "best.pt")),
}


def _resolve_run_id(client, name: str) -> str | None:
    """Resolve the run to pull for a canonical model name.

    Prefers the registry Production version (set by the DAG's promote step);
    falls back to the latest run tagged ``model_name=<name>`` so the sync still
    works when registry registration was skipped (client/server version drift).
    """
    registry_name = f"{_REGISTRY_PREFIX}{name}"
    try:
        versions = client.get_latest_versions(registry_name, stages=["Production"])
        if versions:
            return versions[0].run_id
    except Exception as exc:
        logger.debug("Registry lookup failed for %s: %s", registry_name, exc)

    try:
        experiment = client.get_experiment_by_name(_EXPERIMENT_NAME)
        if experiment is None:
            return None
        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=f"tags.model_name = '{name}'",
            order_by=["start_time DESC"],
            max_results=1,
        )
        return runs[0].info.run_id if runs else None
    except Exception as exc:
        logger.debug("Run search failed for %s: %s", name, exc)
        return None


def _download_artifact(run_id: str, candidates: tuple[str, ...]) -> str | None:
    """Download the first existing artifact candidate; return its local path."""
    import mlflow

    for artifact_path in candidates:
        try:
            local = mlflow.artifacts.download_artifacts(
                run_id=run_id, artifact_path=artifact_path
            )
            if Path(local).is_file():
                return local
        except Exception as exc:
            logger.debug("Artifact %s not available for run %s: %s",
                         artifact_path, run_id, exc)
    return None


def _sync_one(client, name: str, dest: Path, candidates: tuple[str, ...]) -> str:
    run_id = _resolve_run_id(client, name)
    if not run_id:
        return "no_run"

    local = _download_artifact(run_id, candidates)
    if not local:
        return "no_artifact"

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local, dest)
    logger.info("Synced %s <- run %s -> %s", name, run_id, dest)
    return "synced"


def sync_promoted_models() -> dict[str, str]:
    """Pull every canonical model's promoted checkpoint into cv/results/.

    Returns a per-model status map: synced | no_run | no_artifact | error |
    disabled. Never raises.
    """
    if not _SYNC_ENABLED:
        logger.info("Model sync disabled (MODEL_SYNC_ENABLED=false) — skipping")
        return {name: "disabled" for name in _MODELS}

    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except Exception as exc:
        logger.warning("mlflow not importable — skipping model sync: %s", exc)
        return {name: "error" for name in _MODELS}

    mlflow.set_tracking_uri(_MLFLOW_URI)
    client = MlflowClient()

    results: dict[str, str] = {}
    for name, (dest, candidates) in _MODELS.items():
        try:
            results[name] = _sync_one(client, name, dest, candidates)
        except Exception as exc:
            logger.warning("Model sync failed for %s: %s", name, exc)
            results[name] = "error"

    logger.info("Model sync summary: %s", results)
    return results


def fetch_macro_f1_weights() -> dict[str, float]:
    """Return {canonical_name: test_macro_f1} from the latest MLflow run per model.

    This is the documented ensemble weighting scheme (voting weight = test macro-F1,
    fair on the imbalanced 25-class set). Used to override the hardcoded config
    weights at load time — in particular it replaces YOLO's top-1 proxy with its
    real macro-F1 once a run has logged it. Best-effort: returns {} when MLflow is
    unavailable, so the caller falls back to the config weights.
    """
    if not _SYNC_ENABLED:
        return {}
    try:
        import mlflow
        from mlflow.tracking import MlflowClient
    except Exception as exc:
        logger.warning("mlflow not importable — keeping config weights: %s", exc)
        return {}

    mlflow.set_tracking_uri(_MLFLOW_URI)
    client = MlflowClient()
    try:
        experiment = client.get_experiment_by_name(_EXPERIMENT_NAME)
    except Exception:
        experiment = None
    if experiment is None:
        return {}

    weights: dict[str, float] = {}
    for name in _MODELS:
        try:
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string=f"tags.model_name = '{name}'",
                order_by=["start_time DESC"],
                max_results=1,
            )
            if not runs:
                continue
            metrics = runs[0].data.metrics
            score = metrics.get("test_macro_f1") or metrics.get("test_acc")
            if score:
                weights[name] = float(score)
        except Exception as exc:
            logger.debug("macro-F1 lookup failed for %s: %s", name, exc)
    if weights:
        logger.info("Ensemble weights from MLflow macro-F1: %s", weights)
    return weights
