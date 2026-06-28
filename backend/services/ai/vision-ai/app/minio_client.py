"""MinIO upload helper for vision-ai.

Uploads sanitized JPEG images to the vcd-uploads bucket after prediction.
Disabled when MINIO_STORE_UPLOADS != "true".
"""
import asyncio
import io
import json
import logging
import os
from datetime import date

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger("vision_ai.minio")

_ENABLED     = os.getenv("MINIO_STORE_UPLOADS", "false").lower() == "true"
_ENDPOINT    = os.getenv("MINIO_ENDPOINT", "minio:9000")
_USER        = os.getenv("MINIO_ROOT_USER", "minioadmin")
_PASSWORD    = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
_BUCKET      = os.getenv("MINIO_BUCKET_UPLOADS", "vcd-uploads")
_PUBLIC_URL  = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9002")

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(_ENDPOINT, access_key=_USER, secret_key=_PASSWORD, secure=False)
    return _client


_PUBLIC_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": ["*"]},
        "Action": ["s3:GetObject"],
        "Resource": [f"arn:aws:s3:::{_BUCKET}/*"],
    }],
})


def _ensure_bucket(client: Minio) -> None:
    if not client.bucket_exists(_BUCKET):
        client.make_bucket(_BUCKET)
        client.set_bucket_policy(_BUCKET, _PUBLIC_POLICY)
        logger.info("Created public MinIO bucket: %s", _BUCKET)
    else:
        try:
            client.set_bucket_policy(_BUCKET, _PUBLIC_POLICY)
        except Exception:
            pass


def _upload_sync(image_bytes: bytes, object_name: str) -> str:
    client = _get_client()
    _ensure_bucket(client)
    client.put_object(
        bucket_name=_BUCKET,
        object_name=object_name,
        data=io.BytesIO(image_bytes),
        length=len(image_bytes),
        content_type="image/jpeg",
    )
    return f"{_PUBLIC_URL}/{_BUCKET}/{object_name}"


async def upload_image(image_bytes: bytes, image_id: str, disease: str) -> str | None:
    """Upload image to MinIO. Returns the object path, or None if disabled/failed."""
    if not _ENABLED:
        return None
    today = date.today().isoformat()          # e.g. 2026-05-21
    object_name = f"{disease}/{today}/{image_id}.jpg"
    try:
        path = await asyncio.to_thread(_upload_sync, image_bytes, object_name)
        logger.info("Uploaded image to MinIO: %s", path)
        return path
    except S3Error as exc:
        logger.warning("MinIO upload failed: %s", exc)
        return None
