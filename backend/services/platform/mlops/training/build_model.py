"""
Build a torchvision classifier with pretrained weights and a replaced head.

Supported architectures:
    mobilenetv3_large, efficientnet_b0, efficientnet_b3, vit_b_16, resnet50
"""
from __future__ import annotations

import torch.nn as nn
import torchvision.models as tvm


def build_model(config) -> nn.Module:
    """Return a model with ImageNet pretrained backbone and a fresh classifier head.

    Args:
        config: Any object (dataclass, dict) with .arch and .num_classes attrs.
                Accepts dict via DictConfig wrapper if needed.
    """
    arch: str = config.arch if hasattr(config, "arch") else config["arch"]
    num_classes: int = (
        config.num_classes if hasattr(config, "num_classes") else config["num_classes"]
    )

    arch = arch.lower()

    if arch == "mobilenetv3_large":
        model = tvm.mobilenet_v3_large(weights=tvm.MobileNet_V3_Large_Weights.DEFAULT)
        in_features = model.classifier[3].in_features
        model.classifier[3] = nn.Linear(in_features, num_classes)

    elif arch == "efficientnet_b0":
        model = tvm.efficientnet_b0(weights=tvm.EfficientNet_B0_Weights.DEFAULT)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)

    elif arch == "efficientnet_b3":
        model = tvm.efficientnet_b3(weights=tvm.EfficientNet_B3_Weights.DEFAULT)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)

    elif arch == "vit_b_16":
        model = tvm.vit_b_16(weights=tvm.ViT_B_16_Weights.DEFAULT)
        in_features = model.heads.head.in_features
        model.heads.head = nn.Linear(in_features, num_classes)

    elif arch == "resnet50":
        model = tvm.resnet50(weights=tvm.ResNet50_Weights.DEFAULT)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, num_classes)

    else:
        raise ValueError(
            f"Unsupported arch '{arch}'. "
            "Choose from: mobilenetv3_large, efficientnet_b0, efficientnet_b3, "
            "vit_b_16, resnet50"
        )

    return model
