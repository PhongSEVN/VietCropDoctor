"""
DAG: retrain_classifier
Schedule: Weekly Sunday 02:00 UTC

Pipeline:
  check_data_drift → pull_new_data → train_model
  → evaluate_model → promote_model → reload_vision_service

Trigger thủ công với config để chọn model:
  {"model": "mobilenetv3"}   # hoặc efficientnet_b0, resnet50, transformer, yolo
  Nếu không truyền, mặc định train tất cả 5 model.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

_MLFLOW_URI      = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
_EXPERIMENT_NAME = "plant-disease-classification"
# docker-compose mounts ./ml -> /opt/ml (NOT /opt/mlops). The training scripts
# live under the historical doubled path training/classification/training/classification/.
_SCRIPT_BASE     = Path(os.getenv("ML_SCRIPT_BASE",
                                  "/opt/ml/training/classification/training/classification"))
_BASELINE_PATH   = Path("/data/airflow/baseline_stats.json")
_REGISTRY_PATH   = Path("/data/models/model_registry.json")
_DRIFT_CONF_DROP = 0.05
_NEW_SAMPLE_THRESH = 500
_ACC_REGRESSION_TOL = 0.02   # cho phép giảm tối đa 2pp trước khi block promotion

# Read from env so creds match docker-compose (never hardcode the password).
_CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
_CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
_CLICKHOUSE_DB   = os.getenv("CLICKHOUSE_DB", "vietcropdoctor")
_CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
_CLICKHOUSE_PASS = os.getenv("CLICKHOUSE_PASSWORD", "")

# Canonical model keys — identical vocabulary across train tags, MLflow registry
# (VietCropDoctor-<key>), and the serving cv/results/<key>/ directory. The value
# is the on-disk training script folder, which keeps its historical casing.
_MODEL_SCRIPTS = {
    "efficientnet_b0": _SCRIPT_BASE / "EfficientB0"  / "train.py",
    "mobilenetv3":     _SCRIPT_BASE / "MobileNetV3"  / "train.py",
    "resnet50":        _SCRIPT_BASE / "Resnet50"     / "train.py",
    "vit":             _SCRIPT_BASE / "transformer"  / "train.py",
    "yolo":            _SCRIPT_BASE / "Yolo"          / "train_yolo.py",
}


# Helpers

def _get_model_keys(context) -> list[str]:
    """Return list of models to train from DAG conf, or all 5 if not specified."""
    dag_run = context.get("dag_run")
    if dag_run and dag_run.conf:
        model = dag_run.conf.get("model")
        if model:
            if model not in _MODEL_SCRIPTS:
                raise ValueError(f"Unknown model '{model}'. Choices: {list(_MODEL_SCRIPTS)}")
            return [model]
    return list(_MODEL_SCRIPTS.keys())


def _get_latest_run_id(client, model_name: str) -> str | None:
    """Return run_id of the most recent completed run for model_name."""
    import mlflow
    experiment = client.get_experiment_by_name(_EXPERIMENT_NAME)
    if not experiment:
        return None
    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"tags.model_name = '{model_name}'",
        order_by=["start_time DESC"],
        max_results=1,
    )
    return runs[0].info.run_id if runs else None


# Task functions

def check_data_drift(**context) -> None:
    """Compare last-week confidence vs baseline; skip if no drift detected."""
    import clickhouse_connect

    if not _BASELINE_PATH.exists():
        logger.warning("Baseline not found — proceeding with retraining")
        return

    baseline_conf = float(json.loads(_BASELINE_PATH.read_text()).get("avg_confidence", 1.0))

    try:
        client = clickhouse_connect.get_client(
            host=_CLICKHOUSE_HOST, port=_CLICKHOUSE_PORT,
            database=_CLICKHOUSE_DB, username=_CLICKHOUSE_USER, password=_CLICKHOUSE_PASS,
        )
        rows = client.query("""
            SELECT avg(confidence) AS avg_conf, count(*) AS new_samples
            FROM predictions
            WHERE timestamp >= now() - INTERVAL 7 DAY
        """).result_rows

        if not rows or rows[0][1] == 0:
            raise AirflowSkipException("No predictions in last 7 days")

        recent_conf, new_samples = float(rows[0][0]), int(rows[0][1])
    except AirflowSkipException:
        raise
    except Exception as exc:
        logger.warning("ClickHouse unavailable (%s) — proceeding", exc)
        return

    conf_drop = baseline_conf - recent_conf
    logger.info("Drift check: baseline=%.4f recent=%.4f drop=%.4f samples=%d",
                baseline_conf, recent_conf, conf_drop, new_samples)

    if conf_drop <= _DRIFT_CONF_DROP and new_samples <= _NEW_SAMPLE_THRESH:
        raise AirflowSkipException(
            f"No significant drift (drop={conf_drop:.4f}, samples={new_samples})"
        )


def train_model(**context) -> dict[str, str]:
    """Train selected model(s), push run_ids to XCom as {model_name: run_id}."""
    import mlflow

    model_keys = _get_model_keys(context)
    env = {**os.environ, "MLFLOW_TRACKING_URI": _MLFLOW_URI}

    mlflow.set_tracking_uri(_MLFLOW_URI)
    client = mlflow.tracking.MlflowClient()

    run_ids: dict[str, str] = {}

    for model_key in model_keys:
        script = _MODEL_SCRIPTS[model_key]
        if not script.exists():
            logger.error("Script not found for %s: %s", model_key, script)
            continue

        logger.info("Training %s …", model_key)
        result = subprocess.run(
            ["python", str(script)],
            env=env,
            capture_output=True,
            text=True,
            timeout=7200,  # 2h per model
        )

        if result.returncode != 0:
            logger.error("Training failed for %s:\n%s", model_key, result.stderr[-2000:])
            continue

        run_id = _get_latest_run_id(client, model_key)
        if run_id:
            run_ids[model_key] = run_id
            logger.info("Trained %s → run_id=%s", model_key, run_id)
        else:
            logger.warning("Could not find MLflow run for %s after training", model_key)

    if not run_ids:
        raise RuntimeError("All training scripts failed — no run_ids produced")

    return run_ids   # stored in XCom automatically


def evaluate_model(**context) -> None:
    """Compare new model test_acc vs current Production; raise on regression."""
    import mlflow

    ti = context["ti"]
    run_ids: dict[str, str] = ti.xcom_pull(task_ids="train_model")
    if not run_ids:
        raise ValueError("No run_ids from train_model task")

    mlflow.set_tracking_uri(_MLFLOW_URI)
    client = mlflow.tracking.MlflowClient()

    regressions = []
    for model_key, run_id in run_ids.items():
        new_run   = client.get_run(run_id)
        new_acc   = float(new_run.data.metrics.get("test_acc", new_run.data.metrics.get("val_acc", 0.0)))

        # Get Production accuracy for this model
        registry_name = f"VietCropDoctor-{model_key}"
        prod_acc = 0.0
        try:
            prod_versions = client.get_latest_versions(registry_name, stages=["Production"])
            if prod_versions:
                prod_run = client.get_run(prod_versions[0].run_id)
                prod_acc = float(prod_run.data.metrics.get("test_acc", prod_run.data.metrics.get("val_acc", 0.0)))
        except Exception as exc:
            logger.warning("Could not retrieve Production metrics for %s: %s", registry_name, exc)

        logger.info("%s: new_acc=%.4f prod_acc=%.4f", model_key, new_acc, prod_acc)

        if new_acc < prod_acc - _ACC_REGRESSION_TOL:
            regressions.append(
                f"{model_key}: new={new_acc:.4f} < prod={prod_acc:.4f} (tol={_ACC_REGRESSION_TOL})"
            )

    if regressions:
        raise ValueError("Model regression detected:\n" + "\n".join(regressions))


def promote_model(**context) -> None:
    """Promote new model versions to Production in MLflow registry."""
    import mlflow

    ti = context["ti"]
    run_ids: dict[str, str] = ti.xcom_pull(task_ids="train_model")

    mlflow.set_tracking_uri(_MLFLOW_URI)
    client = mlflow.tracking.MlflowClient()

    promoted = []
    for model_key, run_id in run_ids.items():
        registry_name = f"VietCropDoctor-{model_key}"
        try:
            versions = client.search_model_versions(f"run_id='{run_id}'")
            if not versions:
                logger.warning("No registered version for run_id=%s (%s)", run_id, model_key)
                continue

            new_version = str(versions[0].version)
            client.transition_model_version_stage(
                name=registry_name,
                version=new_version,
                stage="Production",
                archive_existing_versions=True,
            )
            logger.info("Promoted %s v%s to Production", registry_name, new_version)
            promoted.append({"model": model_key, "version": new_version, "run_id": run_id})
        except Exception as exc:
            logger.error("Failed to promote %s: %s", model_key, exc)

    if not promoted:
        raise RuntimeError("No models were promoted to Production")

    registry = {
        "promoted_at": datetime.utcnow().isoformat(),
        "models": promoted,
    }
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    logger.info("Registry written to %s", _REGISTRY_PATH)


# DAG definition

default_args = {
    "owner":            "mlops",
    "retries":          1,
    "retry_delay":      timedelta(minutes=10),
    "email_on_failure": False,
}

with DAG(
    dag_id="retrain_classifier",
    description="Weekly automated model retraining with drift detection and MLflow promotion",
    schedule="0 2 * * 0",   # Sunday 02:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["mlops", "vision-ai"],
) as dag:

    t1 = PythonOperator(task_id="check_data_drift",   python_callable=check_data_drift)
    t2 = BashOperator(
        task_id="pull_new_data",
        # Close the data loop: fold expert-verified (gold) + uploaded (pseudo)
        # images from MinIO into the ImageFolder train partition via PySpark
        # (sequential fallback if no JVM). Non-fatal so a fresh-data hiccup never
        # blocks a scheduled retrain on the existing dataset.
        bash_command="cd /opt/ml && python preprocessing/build_training_set.py || true",
    )
    t3 = PythonOperator(task_id="train_model",        python_callable=train_model)
    t4 = PythonOperator(task_id="evaluate_model",     python_callable=evaluate_model)
    t5 = PythonOperator(task_id="promote_model",      python_callable=promote_model)
    t6 = BashOperator(
        task_id="reload_vision_service",
        bash_command="curl -sf -X POST http://vision-ai:8001/admin/reload-model || true",
    )

    t1 >> t2 >> t3 >> t4 >> t5 >> t6
