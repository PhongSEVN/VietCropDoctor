import torch.nn as nn
from torchvision import models

SUPPORTED = ["efficientnet_b0", "resnet50", "mobilenet_v3_large"]


def build_model(backbone: str, num_classes: int, pretrained: bool = True, dropout: float = 0.3) -> nn.Module:
    if backbone == "efficientnet_b0":
        weights = models.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        m = models.efficientnet_b0(weights=weights)
        in_features = m.classifier[1].in_features
        m.classifier[1] = nn.Sequential(nn.Dropout(dropout), nn.Linear(in_features, num_classes))

    elif backbone == "resnet50":
        weights = models.ResNet50_Weights.DEFAULT if pretrained else None
        m = models.resnet50(weights=weights)
        in_features = m.fc.in_features
        m.fc = nn.Sequential(nn.Dropout(dropout), nn.Linear(in_features, num_classes))

    elif backbone == "mobilenet_v3_large":
        weights = models.MobileNet_V3_Large_Weights.DEFAULT if pretrained else None
        m = models.mobilenet_v3_large(weights=weights)
        in_features = m.classifier[3].in_features
        m.classifier[3] = nn.Sequential(nn.Dropout(dropout), nn.Linear(in_features, num_classes))

    else:
        raise ValueError(f"backbone phải là một trong: {SUPPORTED}")

    return m


def freeze_backbone(model: nn.Module, backbone: str) -> None:
    if backbone == "efficientnet_b0":
        for p in model.features.parameters():
            p.requires_grad = False
    elif backbone == "resnet50":
        for name, p in model.named_parameters():
            if "fc" not in name:
                p.requires_grad = False
    elif backbone == "mobilenet_v3_large":
        for p in model.features.parameters():
            p.requires_grad = False


def unfreeze_all(model: nn.Module) -> None:
    for p in model.parameters():
        p.requires_grad = True
