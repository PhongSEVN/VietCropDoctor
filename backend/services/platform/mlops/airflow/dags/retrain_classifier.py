"""
DAG: retrain_classifier
Schedule: Weekly Sunday 02:00 UTC

Pipeline:
  check_data_drift → pull_new_data → train_model
  → evaluate_model → promote_model → reload_vision_service
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator

sys.path.insert(0, "/opt/mlops")   # mounted from services/mlops/

logger = logging.getLogger(__name__)

_BASELINE_PATH      = Path("/data/airflow/baseline_stats.json")
_REGISTRY_PATH      = Path("/data/models/model_registry.json")
_DRIFT_CONF_DROP    = 0.05   # 5 pp drop triggers retraining
_NEW_SAMPLE_THRESH  = 500
_F1_REGRESSION_TOL  = 0.02   # allow 2 pp slack before blocking promotion
_MLFLOW_URI         = "http://mlflow:5000"
_CLICKHOUSE_HOST    = "clickhouse"
_CLICKHOUSE_PORT    = 8123
_CLICKHOUSE_DB      = "vietcropdoctor"
_CLICKHOUSE_USER    = "admin"
_CLICKHOUSE_PASS    = "secret"


# Task functions

def check_data_drift(**context) -> None:
    """Compare last-week confidence vs baseline; skip if no drift detected."""
    import clickhouse_connect

    # Read baseline
    if not _BASELINE_PATH.exists():
        logger.warning("Baseline not found at %s — proceeding with retraining", _BASELINE_PATH)
        return

    baseline = json.loads(_BASELINE_PATH.read_text())
    baseline_conf   = float(baseline.get("avg_confidence", 1.0))

    # Query ClickHouse
    try:
        client = clickhouse_connect.get_client(
            host=_CLICKHOUSE_HOST,
            port=_CLICKHOUSE_PORT,
            database=_CLICKHOUSE_DB,
            username=_CLICKHOUSE_USER,
            password=_CLICKHOUSE_PASS,
        )
        result = client.query("""
            SELECT
                avg(confidence)   AS avg_conf,
                count(*)          AS new_samples
            FROM predictions
            WHERE timestamp >= now() - INTERVAL 7 DAY
        """)
        rows = result.result_rows
        if not rows or rows[0][1] == 0:
            logger.info("No predictions in last 7 days — skipping retraining")
            raise AirflowSkipException("No recent prediction data")

        recent_conf, new_samples = float(rows[0][0]), int(rows[0][1])
    except AirflowSkipException:
        raise
    except Exception as exc:
        logger.warning("ClickHouse unavailable (%s) — proceeding with retraining", exc)
        return

    logger.info(
        "Drift check: baseline_conf=%.4f recent_conf=%.4f new_samples=%d",
        baseline_conf, recent_conf, new_samples,
    )

    conf_drop = baseline_conf - recent_conf
    if conf_drop <= _DRIFT_CONF_DROP and new_samples <= _NEW_SAMPLE_THRESH:
        raise AirflowSkipException(
            f"No significant drift (drop={conf_drop:.4f}, samples={new_samples})"
        )

    logger.info("Drift detected — proceeding with retraining pipeline")


def train_model(**context) -> str:
    """Run training and push run_id to XCom."""
    import os
    import mlflow

    from training.train_classifier import TrainConfig, train

    os.environ["MLFLOW_TRACKING_URI"] = _MLFLOW_URI
    mlflow.set_tracking_uri(_MLFLOW_URI)
    mlflow.set_experiment("VietCropDoctor")

    config = TrainConfig.from_yaml(
        "/opt/mlops/training/configs/mobilenetv3_baseline.yaml"
    )
    run_id = train(config)
    logger.info("Training complete: run_id=%s", run_id)
    return run_id   # stored in XCom automatically by return value


def evaluate_model(**context) -> None:
    """Load metrics from the new run; raise if regression vs production."""
    import mlflow

    ti      = context["ti"]
    run_id  = ti.xcom_pull(task_ids="train_model")
    if not run_id:
        raise ValueError("No run_id from train_model task")

    mlflow.set_tracking_uri(_MLFLOW_URI)
    client  = mlflow.tracking.MlflowClient()
    run     = client.get_run(run_id)
    new_f1  = float(run.data.metrics.get("val_f1", run.data.metrics.get("best_val_acc", 0.0)))

    # Get production model F1
    prod_f1 = 0.0
    try:
        prod_versions = client.get_latest_versions(
            "VietCropDoctor-Classifier", stages=["Production"]
        )
        if prod_versions:
            prod_run = client.get_run(prod_versions[0].run_id)
            prod_f1  = float(prod_run.data.metrics.get("val_f1", 0.0))
    except Exception as exc:
        logger.warning("Could not retrieve production model metrics: %s", exc)

    logger.info("Evaluation: new_f1=%.4f prod_f1=%.4f (tolerance=%.4f)", new_f1, prod_f1, _F1_REGRESSION_TOL)

    if new_f1 < prod_f1 - _F1_REGRESSION_TOL:
        raise ValueError(
            f"Model regression: new val_f1={new_f1:.4f} < prod_f1={prod_f1:.4f} - {_F1_REGRESSION_TOL}"
        )


def promote_model(**context) -> None:
    """Promote new model version to Production in MLflow registry."""
    import mlflow

    ti     = context["ti"]
    run_id = ti.xcom_pull(task_ids="train_model")

    mlflow.set_tracking_uri(_MLFLOW_URI)
    client = mlflow.tracking.MlflowClient()

    versions = client.search_model_versions(f"run_id='{run_id}'")
    if not versions:
        raise ValueError(f"No registered model version found for run_id={run_id}")

    new_version = str(versions[0].version)
    client.transition_model_version_stage(
        name="VietCropDoctor-Classifier",
        version=new_version,
        stage="Production",
        archive_existing_versions=True,
    )
    logger.info("Promoted version=%s to Production", new_version)

    registry = {
        "run_id":       run_id,
        "version":      new_version,
        "stage":        "Production",
        "promoted_at":  datetime.utcnow().isoformat(),
    }
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(registry, indent=2))
    logger.info("Model registry written to %s", _REGISTRY_PATH)


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

    t1 = PythonOperator(
        task_id="check_data_drift",
        python_callable=check_data_drift,
    )

    t2 = BashOperator(
        task_id="pull_new_data",
        bash_command=(
            "cd /opt/mlops && "
            "dvc pull && "
            "python training/data/preprocess.py --incremental || true"
        ),
    )

    t3 = PythonOperator(
        task_id="train_model",
        python_callable=train_model,
    )

    t4 = PythonOperator(
        task_id="evaluate_model",
        python_callable=evaluate_model,
    )

    t5 = PythonOperator(
        task_id="promote_model",
        python_callable=promote_model,
    )

    t6 = BashOperator(
        task_id="reload_vision_service",
        bash_command="curl -sf -X POST http://vision-ai:8001/admin/reload-model || true",
    )

    t1 >> t2 >> t3 >> t4 >> t5 >> t6
