"""MinIO helper for the feedback loop.

When a user verifies (or corrects) a diagnosis, the original uploaded image is
server-side copied from the uploads bucket into a *verified* bucket, keyed by the
human-confirmed disease label:

    vcd-uploads/<predicted>/<date>/<id>.jpg
        → vcd-verified/<confirmed_label>/<date>/<id>.jpg

These verified-label samples are higher quality than the ETL's pseudo-labels and
can be preferred by the retraining pipeline. All operations are best-effort:
any failure returns None and is logged, never raised to the request handler.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date
from pathlib import PurePosixPath
from urllib.parse import urlparse

logger = logging.getLogger("rag_engine.feedback_minio")

_ENDPOINT        = os.getenv("MINIO_ENDPOINT", "minio:9000")
_USER            = os.getenv("MINIO_ROOT_USER", "minioadmin")
_PASSWORD        = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
_UPLOADS_BUCKET  = os.getenv("MINIO_BUCKET_UPLOADS", "vcd-uploads")
_VERIFIED_BUCKET = os.getenv("MINIO_BUCKET_VERIFIED", "vcd-verified")
_PUBLIC_URL      = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9002")

_client = None  # type: ignore[var-annotated]


def _get_client():
    global _client
    if _client is None:
        from minio import Minio
        _client = Minio(_ENDPOINT, access_key=_USER, secret_key=_PASSWORD, secure=False)
    return _client


def _public_read_policy(bucket: str) -> str:
    return json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/*"],
        }],
    })


def _ensure_bucket(client, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    try:
        client.set_bucket_policy(bucket, _public_read_policy(bucket))
    except Exception:
        pass


def _object_key_from_url(image_url: str) -> str | None:
    """Extract the uploads-bucket object key from a public image URL.

    e.g. http://localhost:9002/vcd-uploads/lua___bs/2026-06-05/abc.jpg
         → lua___bs/2026-06-05/abc.jpg
    """
    path = urlparse(image_url).path.lstrip("/")  # vcd-uploads/lua/2026.../abc.jpg
    prefix = f"{_UPLOADS_BUCKET}/"
    if path.startswith(prefix):
        return path[len(prefix):]
    return None


def _copy_sync(src_key: str, confirmed_label: str) -> str | None:
    from minio.commonconfig import CopySource

    client = _get_client()
    _ensure_bucket(client, _VERIFIED_BUCKET)

    image_id = PurePosixPath(src_key).stem
    today = date.today().isoformat()
    dest_key = f"{confirmed_label}/{today}/{image_id}.jpg"

    client.copy_object(
        bucket_name=_VERIFIED_BUCKET,
        object_name=dest_key,
        source=CopySource(_UPLOADS_BUCKET, src_key),
    )
    return f"{_PUBLIC_URL}/{_VERIFIED_BUCKET}/{dest_key}"


async def copy_to_verified(image_url: str | None, confirmed_label: str) -> str | None:
    """Copy the uploaded image into the verified bucket under the confirmed label.

    Returns the verified public URL, or None when there is no source image or the
    copy fails (e.g. MINIO_STORE_UPLOADS was off so the source was never stored).
    """
    if not image_url or not confirmed_label:
        return None
    src_key = _object_key_from_url(image_url)
    if not src_key:
        logger.info("Feedback image_url not in uploads bucket, skipping copy: %s", image_url)
        return None
    try:
        path = await asyncio.to_thread(_copy_sync, src_key, confirmed_label)
        logger.info("Copied verified sample → %s", path)
        return path
    except Exception:
        logger.warning("Failed to copy verified image for label %s", confirmed_label, exc_info=True)
        return None
