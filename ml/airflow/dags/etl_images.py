"""
ETL DAG — runs daily, reads new images from MinIO and adds them to the training dataset.

Trigger: cron schedule (daily at 02:00 ICT)
Steps:
  1. list_new_images        — list images in MinIO vcd-uploads/ newer than the last watermark
  2. validate_images        — download to staging, drop corrupt/unreadable files
  3. run_preprocessing      — resize 224x224 RGB, write into the training dataset partition
  4. commit_state           — advance the watermark + accumulate the pending-image counter
  5. check_retrain_threshold (ShortCircuit) — proceed only when pending >= _RETRAIN_THRESHOLD
  6. publish_retrain_event  — publish `retrain.requested` to Kafka (audit/event)
  7. trigger_retrain        — fire the `retrain_classifier` DAG to close the loop

Self-contained on purpose: the Airflow container does not mount `vcd_shared`, so the
MinIO / Kafka clients and the topic name are wired locally from environment variables.

Images in MinIO are pseudo-labelled by the model's predicted class
(object key layout: `{disease}/{YYYY-MM-DD}/{image_id}.jpg`). The leading path
segment is reused as the dataset class folder, keeping the label space identical
to the classifier's.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

logger = logging.getLogger(__name__)

# Configuration (from env, with dev defaults matching docker-compose)
_MINIO_ENDPOINT  = os.getenv("MINIO_ENDPOINT", "minio:9000")
_MINIO_USER      = os.getenv("MINIO_ROOT_USER", "minioadmin")
_MINIO_PASSWORD  = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
_BUCKET          = os.getenv("MINIO_BUCKET_UPLOADS", "vcd-uploads")
_KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")

_TOPIC_RETRAIN     = "retrain.requested"
_RETRAIN_THRESHOLD = int(os.getenv("ETL_RETRAIN_THRESHOLD", "100"))
_TARGET_SIZE       = (224, 224)
_VALID_EXTS        = {".jpg", ".jpeg", ".png", ".webp"}

_STATE_PATH       = Path("/data/airflow/etl_images_state.json")
_INCREMENTAL_DIR  = Path("/data/training/incremental")
_STAGING_ROOT     = Path("/data/training/_staging")

default_args = {
    "owner": "vietcropdoctor",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


# State helpers

def _load_state() -> dict:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text())
        except (json.JSONDecodeError, ValueError):
            logger.warning("Corrupt state file %s — resetting", _STATE_PATH)
    return {"last_modified": None, "pending_count": 0}


def _save_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2))


def _minio_client():
    from minio import Minio  # imported lazily so DAG parsing never fails

    return Minio(
        _MINIO_ENDPOINT,
        access_key=_MINIO_USER,
        secret_key=_MINIO_PASSWORD,
        secure=False,
    )


# Task functions

def list_new_images(**context) -> dict:
    """List MinIO objects newer than the stored watermark.

    Returns (via XCom) {"objects": [...], "max_modified": iso|None}.
    Skips the whole pipeline when nothing new has arrived.
    """
    state    = _load_state()
    raw_mark = state.get("last_modified")
    watermark = datetime.fromisoformat(raw_mark) if raw_mark else None

    client = _minio_client()
    if not client.bucket_exists(_BUCKET):
        raise AirflowSkipException(f"Bucket '{_BUCKET}' does not exist yet — nothing to ETL")

    new_objects: list[dict] = []
    max_modified = watermark
    for obj in client.list_objects(_BUCKET, recursive=True):
        suffix = Path(obj.object_name).suffix.lower()
        if suffix not in _VALID_EXTS:
            continue

        modified = obj.last_modified  # tz-aware datetime
        if watermark is not None and modified <= watermark:
            continue

        parts   = obj.object_name.split("/")
        disease = parts[0] if len(parts) > 1 else "unlabeled"
        new_objects.append(
            {
                "object_name": obj.object_name,
                "disease": disease,
                "image_id": Path(obj.object_name).stem,
                "last_modified": modified.isoformat(),
            }
        )
        if max_modified is None or modified > max_modified:
            max_modified = modified

    if not new_objects:
        raise AirflowSkipException("No new images in MinIO since last run")

    logger.info("Found %d new image(s) since %s", len(new_objects), raw_mark or "<beginning>")
    return {
        "objects": new_objects,
        "max_modified": max_modified.isoformat() if max_modified else None,
    }


def validate_images(**context) -> list[dict]:
    """Download new objects to a per-run staging dir and drop corrupt files."""
    from PIL import Image, UnidentifiedImageError

    ti      = context["ti"]
    listing = ti.xcom_pull(task_ids="list_new_images") or {}
    objects = listing.get("objects", [])
    if not objects:
        raise AirflowSkipException("Nothing to validate")

    run_id      = context["run_id"].replace(":", "_").replace("+", "_")
    staging_dir = _STAGING_ROOT / run_id
    staging_dir.mkdir(parents=True, exist_ok=True)

    client = _minio_client()
    valid: list[dict] = []
    removed = 0
    for item in objects:
        dst = staging_dir / item["disease"] / f"{item['image_id']}{Path(item['object_name']).suffix.lower()}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            client.fget_object(_BUCKET, item["object_name"], str(dst))
            with Image.open(dst) as img:
                img.verify()  # integrity check without decoding the full image
            valid.append({**item, "staged_path": str(dst)})
        except (UnidentifiedImageError, OSError, Exception) as exc:
            logger.warning("Dropping unreadable image %s: %s", item["object_name"], exc)
            Path(dst).unlink(missing_ok=True)
            removed += 1

    logger.info("Validation: %d valid, %d removed", len(valid), removed)
    if not valid:
        raise AirflowSkipException("All downloaded images were corrupt")
    return valid


def run_preprocessing(**context) -> int:
    """Resize validated images to 224x224 and write them into the dataset partition."""
    from PIL import Image

    ti    = context["ti"]
    valid = ti.xcom_pull(task_ids="validate_images") or []
    if not valid:
        raise AirflowSkipException("Nothing to preprocess")

    written = 0
    for item in valid:
        out_path = _INCREMENTAL_DIR / item["disease"] / f"{item['image_id']}.jpg"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(item["staged_path"]) as img:
                img = img.convert("RGB").resize(_TARGET_SIZE, Image.LANCZOS)
                img.save(out_path, format="JPEG", quality=90)
            written += 1
        except Exception as exc:
            logger.warning("Failed to preprocess %s: %s", item["staged_path"], exc)

    logger.info("Preprocessing: wrote %d image(s) to %s", written, _INCREMENTAL_DIR)
    return written


def commit_state(**context) -> int:
    """Advance the watermark and accumulate the pending-image counter.

    Runs regardless of the retrain threshold so progress is never reprocessed.
    Returns the new pending count.
    """
    ti       = context["ti"]
    listing  = ti.xcom_pull(task_ids="list_new_images") or {}
    written  = int(ti.xcom_pull(task_ids="run_preprocessing") or 0)
    max_mark = listing.get("max_modified")

    state = _load_state()
    if max_mark:
        state["last_modified"] = max_mark
    state["pending_count"] = int(state.get("pending_count", 0)) + written
    _save_state(state)

    logger.info(
        "State committed: watermark=%s pending_count=%d (+%d)",
        max_mark, state["pending_count"], written,
    )
    return state["pending_count"]


def check_retrain_threshold(**context) -> bool:
    """Short-circuit gate: proceed only when enough new images have accumulated.

    On trigger, resets the pending counter and stores the count in XCom so the
    publish task can include it in the event payload.
    """
    ti      = context["ti"]
    pending = int(ti.xcom_pull(task_ids="commit_state") or 0)

    if pending < _RETRAIN_THRESHOLD:
        logger.info("Pending %d < threshold %d — not requesting retrain", pending, _RETRAIN_THRESHOLD)
        return False

    state = _load_state()
    state["pending_count"] = 0
    _save_state(state)

    ti.xcom_push(key="accumulated", value=pending)
    logger.info("Pending %d >= threshold %d — requesting retrain", pending, _RETRAIN_THRESHOLD)
    return True


def publish_retrain_event(**context) -> None:
    """Publish a `retrain.requested` event to Kafka (mirrors the shared envelope)."""
    from kafka import KafkaProducer

    ti          = context["ti"]
    accumulated = int(ti.xcom_pull(task_ids="check_retrain_threshold", key="accumulated") or 0)

    message = {
        "event_type": "retrain.requested",
        "payload": {
            "reason": "etl_threshold",
            "accumulated_images": accumulated,
            "threshold": _RETRAIN_THRESHOLD,
            "dataset_dir": str(_INCREMENTAL_DIR),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "airflow-etl",
        "trace_id": str(uuid.uuid4()),
    }

    producer = KafkaProducer(
        bootstrap_servers=_KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(),
        acks="all",
        retries=3,
    )
    try:
        producer.send(_TOPIC_RETRAIN, message).get(timeout=10)
        logger.info("Published retrain.requested (accumulated=%d)", accumulated)
    finally:
        producer.flush()
        producer.close()


with DAG(
    dag_id="etl_images",
    default_args=default_args,
    description="Daily ETL: MinIO uploads -> validated + preprocessed training images",
    schedule_interval="0 19 * * *",  # 02:00 ICT = 19:00 UTC
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["etl", "images", "mlops"],
) as dag:

    list_images = PythonOperator(task_id="list_new_images", python_callable=list_new_images)
    validate    = PythonOperator(task_id="validate_images", python_callable=validate_images)
    preprocess  = PythonOperator(task_id="run_preprocessing", python_callable=run_preprocessing)
    commit      = PythonOperator(task_id="commit_state", python_callable=commit_state)

    threshold_gate = ShortCircuitOperator(
        task_id="check_retrain_threshold",
        python_callable=check_retrain_threshold,
    )

    publish_event = PythonOperator(
        task_id="publish_retrain_event",
        python_callable=publish_retrain_event,
    )

    trigger_retrain = TriggerDagRunOperator(
        task_id="trigger_retrain",
        trigger_dag_id="retrain_classifier",
        wait_for_completion=False,
        reset_dag_run=True,
    )

    list_images >> validate >> preprocess >> commit >> threshold_gate
    threshold_gate >> publish_event >> trigger_retrain
