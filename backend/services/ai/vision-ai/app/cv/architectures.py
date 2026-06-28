"""
Serving-side architecture builders that match the trained checkpoints exactly.

All four torch classifiers were trained with the same rich classifier head
``[BatchNorm1d, Linear(in, 256), ReLU, Dropout, Linear(256, num_classes)]``
(ViT uses ``LayerNorm`` instead of ``BatchNorm1d``). The serving models in
``cv/<arch>/model.py`` use a *simpler* head, so loading a trained checkpoint into
them fails silently and the service drops to mock mode. These builders reproduce
the training-time architecture so ``load_state_dict(..., strict=True)`` succeeds.

State-dict key prefixes produced by each builder (must match the .pth files):
  efficientnet_b0  →  features.*            classifier.1.*      (bare torchvision model)
  mobilenet_v3     →  backbone.features.*   backbone.classifier.3.*
  resnet50         →  backbone.conv1.*      backbone.fc.*
  vit              →  backbone.embeddings.* classifier.*
"""
from __future__ import annotations

import torch.nn as nn
from torchvision import models

_HIDDEN = 256


def _cnn_head(in_features: int, num_classes: int, dropout: float) -> nn.Sequential:
    """Shared classifier head for the three CNNs (BatchNorm variant)."""
    return nn.Sequential(
        nn.BatchNorm1d(in_features),
        nn.Linear(in_features, _HIDDEN),
        nn.ReLU(),
        nn.Dropout(dropout),
        nn.Linear(_HIDDEN, num_classes),
    )


def build_efficientnet_b0(num_classes: int, dropout: float = 0.3) -> nn.Module:
    """Bare torchvision efficientnet_b0 with the trained head at classifier[1].

    Returned model has NO ``backbone.`` prefix — matches checkpoints saved from
    the training ``build_model`` which returns the torchvision model directly.
    """
    m = models.efficientnet_b0(weights=None)
    in_features = m.classifier[1].in_features
    m.classifier[1] = _cnn_head(in_features, num_classes, dropout)
    return m


class _MobileNetV3(nn.Module):
    def __init__(self, num_classes: int, dropout: float = 0.3) -> None:
        super().__init__()
        self.backbone = models.mobilenet_v3_large(weights=None)
        in_features = self.backbone.classifier[3].in_features
        self.backbone.classifier[3] = _cnn_head(in_features, num_classes, dropout)

    def forward(self, x):
        return self.backbone(x)


class _ResNet50(nn.Module):
    def __init__(self, num_classes: int, dropout: float = 0.3) -> None:
        super().__init__()
        self.backbone = models.resnet50(weights=None)
        in_features = self.backbone.fc.in_features
        self.backbone.fc = _cnn_head(in_features, num_classes, dropout)

    def forward(self, x):
        return self.backbone(x)


class _ViT(nn.Module):
    """Vision Transformer matching the trained ``ViTForPlantDisease``.

    Built from ``ViTConfig`` (no network access) since the checkpoint already
    carries the full backbone weights, including the pooler.
    """

    def __init__(self, num_classes: int, dropout: float = 0.3) -> None:
        super().__init__()
        from transformers import ViTConfig, ViTModel

        # google/vit-base-patch16-224 hyper-parameters.
        config = ViTConfig(
            hidden_size=768,
            num_hidden_layers=12,
            num_attention_heads=12,
            intermediate_size=3072,
            image_size=224,
            patch_size=16,
            num_channels=3,
        )
        self.backbone = ViTModel(config)  # add_pooling_layer=True by default
        hidden_size = config.hidden_size
        self.classifier = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, _HIDDEN),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(_HIDDEN, num_classes),
        )

    def forward(self, pixel_values):
        outputs = self.backbone(pixel_values=pixel_values)
        cls_output = outputs.last_hidden_state[:, 0, :]
        return self.classifier(cls_output)


# Maps the ``backbone`` field stored in a checkpoint → builder fn.
# Values seen in checkpoints: efficientnet_b0 / mobilenetv3 / resnet50 /
# transformer-vit-base-patch16-224.
_BUILDERS = {
    "efficientnet_b0": build_efficientnet_b0,
    "mobilenetv3": lambda n, d=0.3: _MobileNetV3(n, d),
    "mobilenet_v3_large": lambda n, d=0.3: _MobileNetV3(n, d),
    "resnet50": lambda n, d=0.3: _ResNet50(n, d),
    "vit": lambda n, d=0.3: _ViT(n, d),
}


def build_architecture(arch: str, num_classes: int, dropout: float = 0.3) -> nn.Module:
    """Build a serving architecture by name.

    Args:
        arch: One of the keys in ``_BUILDERS``; the checkpoint ``backbone`` field
            is normalised before lookup (a ``transformer-vit-*`` value maps to vit).
        num_classes: Output classes.
        dropout: Head dropout (irrelevant at eval, kept for shape parity).

    Raises:
        KeyError: if ``arch`` is unknown.
    """
    key = arch.strip().lower()
    if key.startswith("transformer-vit") or key.startswith("vit"):
        key = "vit"
    if key not in _BUILDERS:
        raise KeyError(f"Unknown architecture '{arch}' (normalised '{key}')")
    return _BUILDERS[key](num_classes, dropout)
