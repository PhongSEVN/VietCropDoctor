"""
Image validation — filter out corrupt or unreadable files before training.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


def validate_directory(directory: str | Path) -> tuple[int, int]:
    """Check all images in directory tree. Returns (valid_count, removed_count)."""
    root = Path(directory)
    valid = removed = 0

    for img_path in root.rglob("*"):
        if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        try:
            with Image.open(img_path) as img:
                img.verify()
            valid += 1
        except (UnidentifiedImageError, Exception) as exc:
            logger.warning("Removing corrupt image %s: %s", img_path, exc)
            img_path.unlink(missing_ok=True)
            removed += 1

    logger.info("Validation complete: %d valid, %d removed", valid, removed)
    return valid, removed
