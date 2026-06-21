"""Vision Transformer model for plant disease classification."""
import torch
import torch.nn as nn
from transformers import ViTModel, ViTImageProcessor
from typing import Optional


class ViTForPlantDisease(nn.Module):
    """Vision Transformer for plant disease classification."""
    
    def __init__(
        self,
        num_classes: int = 4,
        model_name: str = 'google/vit-base-patch16-224',
        dropout: float = 0.3,
        frozen_backbone: bool = False
    ):
        """
        Initialize Vision Transformer model.
        
        Args:
            num_classes: Number of disease classes
            model_name: Pretrained model name from HuggingFace
            dropout: Dropout rate for classifier head
            frozen_backbone: Whether to freeze backbone
        """
        super().__init__()
        self.num_classes = num_classes
        self.model_name = model_name
        
        # Load pretrained Vision Transformer
        self.backbone = ViTModel.from_pretrained(model_name)
        hidden_size = self.backbone.config.hidden_size
        
        # Classification head
        self.classifier = nn.Sequential(
            nn.LayerNorm(hidden_size),
            nn.Linear(hidden_size, 256),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, num_classes),
        )
        
        if frozen_backbone:
            self.freeze_backbone()
    
    def freeze_backbone(self):
        """Freeze all backbone parameters."""
        for param in self.backbone.parameters():
            param.requires_grad = False
    
    def unfreeze_backbone(self):
        """Unfreeze all backbone parameters."""
        for param in self.backbone.parameters():
            param.requires_grad = True
    
    def forward(self, pixel_values):
        """
        Forward pass.
        
        Args:
            pixel_values: Input tensor of shape [B, 3, 224, 224]
            
        Returns:
            logits: Classification logits of shape [B, num_classes]
        """
        # Get embeddings from ViT
        outputs = self.backbone(pixel_values=pixel_values)
        
        # Use [CLS] token
        cls_output = outputs.last_hidden_state[:, 0, :]
        
        # Classification
        logits = self.classifier(cls_output)
        
        return logits


def build_transformer_model(
    num_classes: int,
    model_name: str = 'google/vit-base-patch16-224',
    dropout: float = 0.3,
    pretrained: bool = True,
    frozen_backbone: bool = False
) -> ViTForPlantDisease:
    """
    Build Vision Transformer model.
    
    Args:
        num_classes: Number of classes
        model_name: Model name from HuggingFace
        dropout: Dropout rate
        pretrained: Use pretrained weights
        frozen_backbone: Freeze backbone
        
    Returns:
        ViTForPlantDisease model
    """
    model = ViTForPlantDisease(
        num_classes=num_classes,
        model_name=model_name,
        dropout=dropout,
        frozen_backbone=frozen_backbone
    )
    return model


def get_image_processor(model_name: str = 'google/vit-base-patch16-224'):
    """Get image processor for model."""
    return ViTImageProcessor.from_pretrained(model_name)