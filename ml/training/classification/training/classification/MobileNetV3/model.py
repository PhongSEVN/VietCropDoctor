"""MobileNetV3 model for plant disease classification."""
import torch.nn as nn
from torchvision import models


class MobileNetV3Classifier(nn.Module):
    """MobileNetV3-Large for plant disease classification."""

    def __init__(
        self,
        num_classes: int = 4,
        dropout: float = 0.3,
        frozen_backbone: bool = False,
        pretrained: bool = True,
    ):
        """
        Initialize MobileNetV3 model.

        Args:
            num_classes: Number of disease classes
            dropout: Dropout rate for classifier head
            frozen_backbone: Whether to freeze backbone
            pretrained: Use pretrained weights
        """
        super().__init__()
        self.num_classes = num_classes

        # Load pretrained MobileNetV3-Large
        weights = models.MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
        self.backbone = models.mobilenet_v3_large(weights=weights)

        # Replace classifier head
        in_features = self.backbone.classifier[3].in_features
        self.backbone.classifier[3] = nn.Sequential(
            nn.BatchNorm1d(in_features),
            nn.Linear(in_features, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes),
        )

        if frozen_backbone:
            self.freeze_backbone()

    def freeze_backbone(self):
        """Freeze all backbone parameters except classifier."""
        for param in self.backbone.features.parameters():
            param.requires_grad = False

    def unfreeze_backbone(self):
        """Unfreeze all backbone parameters."""
        for param in self.backbone.parameters():
            param.requires_grad = True

    def forward(self, x):
        """
        Forward pass.

        Args:
            x: Input tensor of shape [B, 3, 224, 224]

        Returns:
            logits: Classification logits of shape [B, num_classes]
        """
        return self.backbone(x)


def build_mobilenetv3_model(
    num_classes: int,
    dropout: float = 0.3,
    pretrained: bool = True,
    frozen_backbone: bool = False,
) -> MobileNetV3Classifier:
    """
    Build MobileNetV3 model.

    Args:
        num_classes: Number of classes
        dropout: Dropout rate
        pretrained: Use pretrained weights
        frozen_backbone: Freeze backbone

    Returns:
        MobileNetV3Classifier model
    """
    return MobileNetV3Classifier(
        num_classes=num_classes,
        dropout=dropout,
        pretrained=pretrained,
        frozen_backbone=frozen_backbone,
    )
