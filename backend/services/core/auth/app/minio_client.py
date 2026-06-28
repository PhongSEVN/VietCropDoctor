"""MinIO avatar storage for auth service.

Avatars are stored in the public bucket 'vcd-avatars'.
Object name format: {user_id}.jpg  (overwrite on re-upload)
"""
import asyncio
import io
import json
import logging
import os

from minio import Minio
from minio.error import S3Error

logger = logging.getLogger("auth.minio")

_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
_USER     = os.getenv("MINIO_ROOT_USER", "minioadmin")
_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

AVATAR_BUCKET = "vcd-avatars"

_PUBLIC_POLICY = json.dumps({
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"AWS": ["*"]},
        "Action": ["s3:GetObject"],
        "Resource": [f"arn:aws:s3:::{AVATAR_BUCKET}/*"],
    }],
})

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(_ENDPOINT, access_key=_USER, secret_key=_PASSWORD, secure=False)
    return _client


def _ensure_bucket(client: Minio) -> None:
    if not client.bucket_exists(AVATAR_BUCKET):
        client.make_bucket(AVATAR_BUCKET)
        client.set_bucket_policy(AVATAR_BUCKET, _PUBLIC_POLICY)
        logger.info("Created public MinIO bucket: %s", AVATAR_BUCKET)


def _upload_sync(image_bytes: bytes, object_name: str, content_type: str) -> None:
    client = _get_client()
    _ensure_bucket(client)
    client.put_object(
        bucket_name=AVATAR_BUCKET,
        object_name=object_name,
        data=io.BytesIO(image_bytes),
        length=len(image_bytes),
        content_type=content_type,
    )


async def upload_avatar(image_bytes: bytes, user_id: str, content_type: str = "image/jpeg") -> str:
    """Upload avatar to MinIO. Returns object_name stored in DB (e.g. '{user_id}.jpg')."""
    ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
    object_name = f"{user_id}.{ext}"
    try:
        await asyncio.to_thread(_upload_sync, image_bytes, object_name, content_type)
        logger.info("Uploaded avatar: %s/%s", AVATAR_BUCKET, object_name)
    except S3Error as exc:
        logger.error("MinIO avatar upload failed: %s", exc)
        raise RuntimeError(f"Avatar upload failed: {exc}") from exc
    return object_name
