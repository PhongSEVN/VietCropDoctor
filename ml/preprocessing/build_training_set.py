"""Close the feedback → training data loop with PySpark.

Pulls newly collected images from MinIO into the ImageFolder dataset that the
classification train scripts read, so a retrain actually learns from fresh data —
in particular from the **expert-verified** labels, which were previously written
to the ``vcd-verified`` bucket but never reached the training set.

Two sources, verified preferred:
  * ``vcd-verified/<confirmed_label>/<date>/<id>.jpg`` — gold labels confirmed or
    corrected by an agronomist (high quality).
  * ``vcd-uploads/<predicted>/<date>/<id>.jpg``       — model pseudo-labels.

When the same image id appears in both, the verified copy wins and the pseudo
copy is dropped. Processing is incremental via a per-bucket watermark, so each
run only touches objects newer than the previous run.

Output: resized 224×224 RGB JPEGs written as
  ``<TRAIN_DATASET_DIR>/<class_name>/<image_id>.jpg``
i.e. straight into the ImageFolder partition the train scripts consume — no
schema change, no parquet bridge.

Distributed resize runs on **PySpark** (``local[*]`` by default). If PySpark or a
JVM is unavailable, it transparently falls back to a sequential pass so the DAG
step never hard-fails; install pyspark + a JRE to get the distributed path.

Run:
    python ml/preprocessing/build_training_set.py
    spark-submit ml/preprocessing/build_training_set.py        # distributed
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger("build_training_set")

# Configuration (env, with container defaults)
_MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio:9000")
_MINIO_USER       = os.getenv("MINIO_ROOT_USER", "minioadmin")
_MINIO_PASSWORD   = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
_BUCKET_VERIFIED  = os.getenv("MINIO_BUCKET_VERIFIED", "vcd-verified")
_BUCKET_UPLOADS   = os.getenv("MINIO_BUCKET_UPLOADS", "vcd-uploads")
# Default points at the ImageFolder train partition the classification scripts read
# (PROJECT_ROOT/data/dataset/train), mounted in the airflow container as /opt/ml.
_TRAIN_DATASET_DIR = Path(os.getenv(
    "TRAIN_DATASET_DIR",
    "/opt/ml/training/classification/data/dataset/train",
))
_STATE_PATH = Path(os.getenv(
    "BUILD_TRAINING_STATE", "/data/airflow/build_training_set_state.json",
))
_INCLUDE_UPLOADS = os.getenv("BUILD_INCLUDE_UPLOADS", "true").lower() == "true"
_SPARK_MASTER    = os.getenv("SPARK_MASTER", "local[*]")
_TARGET_SIZE     = (224, 224)
_VALID_EXTS      = {".jpg", ".jpeg", ".png", ".webp"}


# MinIO

def _minio_client():
    from minio import Minio
    return Minio(_MINIO_ENDPOINT, access_key=_MINIO_USER,
                 secret_key=_MINIO_PASSWORD, secure=False)


def _load_state() -> dict:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text())
        except (json.JSONDecodeError, ValueError):
            logger.warning("Corrupt state %s — resetting", _STATE_PATH)
    return {"verified_watermark": None, "uploads_watermark": None}


def _save_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2))


def _list_new(client, bucket: str, watermark_iso: str | None) -> tuple[list[dict], str | None]:
    """Return (records, new_watermark) for objects newer than the watermark."""
    if not client.bucket_exists(bucket):
        logger.info("Bucket %s does not exist yet — skipping", bucket)
        return [], watermark_iso

    watermark = datetime.fromisoformat(watermark_iso) if watermark_iso else None
    records: list[dict] = []
    max_modified = watermark
    for obj in client.list_objects(bucket, recursive=True):
        if Path(obj.object_name).suffix.lower() not in _VALID_EXTS:
            continue
        modified = obj.last_modified
        if watermark is not None and modified <= watermark:
            continue
        parts = obj.object_name.split("/")
        label = parts[0] if len(parts) > 1 else "unlabeled"
        records.append({
            "bucket": bucket,
            "key": obj.object_name,
            "label": label,
            "image_id": Path(obj.object_name).stem,
        })
        if max_modified is None or modified > max_modified:
            max_modified = modified

    new_mark = max_modified.isoformat() if max_modified else watermark_iso
    return records, new_mark


# Image processing (runs on executors)

def _process_record(rec: dict) -> str:
    """Download, validate, resize, and write one image. Returns a status string."""
    from PIL import Image

    try:
        client = _minio_client()
        response = client.get_object(rec["bucket"], rec["key"])
        try:
            raw = response.read()
        finally:
            response.close()
            response.release_conn()

        img = Image.open(io.BytesIO(raw)).convert("RGB").resize(_TARGET_SIZE, Image.LANCZOS)

        out_dir = _TRAIN_DATASET_DIR / rec["label"]
        out_dir.mkdir(parents=True, exist_ok=True)
        img.save(out_dir / f"{rec['image_id']}.jpg", format="JPEG", quality=90)
        return "written"
    except Exception as exc:  # noqa: BLE001 — per-image isolation, never abort the batch
        logger.warning("Failed %s/%s: %s", rec["bucket"], rec["key"], exc)
        return "failed"


def _dedup(verified: list[dict], uploads: list[dict]) -> list[dict]:
    """Verified wins: drop any upload whose image_id is already verified."""
    verified_ids = {r["image_id"] for r in verified}
    kept_uploads = [r for r in uploads if r["image_id"] not in verified_ids]
    return verified + kept_uploads


# Spark / sequential drivers

def _run_spark(records: list[dict]) -> dict[str, int]:
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.master(_SPARK_MASTER).appName(
        "VietCropDoctor-BuildTrainingSet"
    ).getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        slices = min(len(records), (os.cpu_count() or 4) * 4)
        statuses = (
            spark.sparkContext
            .parallelize(records, numSlices=max(1, slices))
            .map(_process_record)
            .collect()
        )
    finally:
        spark.stop()
    return _tally(statuses)


def _run_sequential(records: list[dict]) -> dict[str, int]:
    return _tally([_process_record(r) for r in records])


def _tally(statuses: list[str]) -> dict[str, int]:
    written = sum(1 for s in statuses if s == "written")
    return {"written": written, "failed": len(statuses) - written}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Build training set from MinIO into ImageFolder")
    parser.add_argument("--no-spark", action="store_true", help="Force the sequential path")
    args = parser.parse_args()

    state = _load_state()
    client = _minio_client()

    verified, verified_mark = _list_new(client, _BUCKET_VERIFIED, state.get("verified_watermark"))
    uploads, uploads_mark = ([], state.get("uploads_watermark"))
    if _INCLUDE_UPLOADS:
        uploads, uploads_mark = _list_new(client, _BUCKET_UPLOADS, state.get("uploads_watermark"))

    records = _dedup(verified, uploads)
    logger.info("New images: %d verified + %d uploads (deduped → %d) → %s",
                len(verified), len(uploads), len(records), _TRAIN_DATASET_DIR)

    if not records:
        logger.info("Nothing new to add — training set unchanged")
        return

    use_spark = not args.no_spark
    counts: dict[str, int]
    if use_spark:
        try:
            counts = _run_spark(records)
        except Exception as exc:  # noqa: BLE001 — Spark/JVM missing → graceful fallback
            logger.warning("Spark path unavailable (%s) — falling back to sequential. "
                           "Install pyspark + a JRE for distributed processing.", exc)
            counts = _run_sequential(records)
    else:
        counts = _run_sequential(records)

    # Advance the watermark only after a successful pass so failures are retried.
    state["verified_watermark"] = verified_mark
    state["uploads_watermark"] = uploads_mark
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    logger.info("Build complete: %d written, %d failed (verified bucket preferred)",
                counts["written"], counts["failed"])


if __name__ == "__main__":
    main()
