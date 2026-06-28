"""ResNet50 model for plant disease classification."""
import torch
import torch.nn as nn
from torchvision import models
from typing import Optional


class ResNet50Classifier(nn.Module):
    """ResNet50 for plant disease classification."""
    
    def __init__(
        self,
        num_classes: int = 4,
        dropout: float = 0.3,
        frozen_backbone: bool = False,
        pretrained: bool = True
    ):
        """
        Initialize ResNet50 model.
        
        Args:
            num_classes: Number of disease classes
            dropout: Dropout rate for classifier head
            frozen_backbone: Whether to freeze backbone
            pretrained: Use pretrained weights
        """
        super().__init__()
        self.num_classes = num_classes
        
        # Load pretrained ResNet50
        weights = models.ResNet50_Weights.DEFAULT if pretrained else None
        self.backbone = models.resnet50(weights=weights)
        
        # Get input features of classifier
        in_features = self.backbone.fc.in_features
        
        # Replace classifier
        self.backbone.fc = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(in_features, num_classes)
        )
        
        if frozen_backbone:
            self.freeze_backbone()
    
    def freeze_backbone(self):
        """Freeze all backbone parameters except classifier."""
        for name, param in self.backbone.named_parameters():
            if "fc" not in name:
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


def build_resnet50_model(
    num_classes: int,
    dropout: float = 0.3,
    pretrained: bool = True,
    frozen_backbone: bool = False
) -> ResNet50Classifier:
    """
    Build ResNet50 model.
    
    Args:
        num_classes: Number of classes
        dropout: Dropout rate
        pretrained: Use pretrained weights
        frozen_backbone: Freeze backbone
        
    Returns:
        ResNet50Classifier model
    """
    model = ResNet50Classifier(
        num_classes=num_classes,
        dropout=dropout,
        pretrained=pretrained,
        frozen_backbone=frozen_backbone
    )
    return model
