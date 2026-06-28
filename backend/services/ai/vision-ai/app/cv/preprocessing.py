"""
Image preprocessing utilities for CV inference.
"""
from __future__ import annotations

import io

import torchvision.transforms as T
from PIL import Image

_IMAGE_SIZE = 224
_NORMALIZE_MEAN = [0.485, 0.456, 0.406]
_NORMALIZE_STD  = [0.229, 0.224, 0.225]

DEFAULT_TRANSFORM = T.Compose([
    T.Resize((_IMAGE_SIZE, _IMAGE_SIZE)),
    T.ToTensor(),
    T.Normalize(_NORMALIZE_MEAN, _NORMALIZE_STD),
])


def load_image_tensor(image_bytes: bytes):
    """Convert raw image bytes to a normalised [1, 3, H, W] tensor."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return DEFAULT_TRANSFORM(img).unsqueeze(0)
