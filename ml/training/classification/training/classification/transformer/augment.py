"""AugmentParser for handling image augmentations in Vision Transformer training."""
import torch
import torchvision.transforms as T
from typing import Dict, Any, Optional


class AugmentParser:
    """Parse augmentation config and build torchvision transforms."""
    
    def __init__(self, config: Dict[str, Any], image_size: int, train: bool = True):
        """
        Initialize AugmentParser.
        
        Args:
            config: Augmentation configuration dictionary
            image_size: Target image size
            train: Whether to apply training augmentations
        """
        self.config = config
        self.image_size = image_size
        self.train = train
    
    def build_transforms(self) -> T.Compose:
        """Build the augmentation pipeline."""
        ops = []
        aug_cfg = self.config.get("augmentation", {})
        
        # Resize
        ops.append(T.Resize((self.image_size, self.image_size)))
        
        if self.train:
            # Random horizontal flip
            if aug_cfg.get("random_horizontal_flip", False):
                ops.append(T.RandomHorizontalFlip(p=0.5))
            
            # Random vertical flip
            if aug_cfg.get("random_vertical_flip", False):
                ops.append(T.RandomVerticalFlip(p=0.5))
            
            # Random rotation
            rotation = aug_cfg.get("random_rotation", 0)
            if rotation > 0:
                ops.append(T.RandomRotation(degrees=rotation))
            
            # Color jitter
            cj = aug_cfg.get("color_jitter", {})
            if cj:
                ops.append(T.ColorJitter(
                    brightness=cj.get("brightness", 0),
                    contrast=cj.get("contrast", 0),
                    saturation=cj.get("saturation", 0),
                    hue=cj.get("hue", 0)
                ))
            
            # Random affine
            affine = aug_cfg.get("random_affine", {})
            if affine:
                ops.append(T.RandomAffine(
                    degrees=affine.get("degrees", 0),
                    translate=affine.get("translate"),
                    scale=affine.get("scale"),
                    shear=affine.get("shear")
                ))
            
            # Gaussian blur
            if aug_cfg.get("gaussian_blur", False):
                ops.append(T.GaussianBlur(kernel_size=3, sigma=(0.1, 2.0)))
        
        # To tensor and normalize
        ops.append(T.ToTensor())
        
        mean = aug_cfg.get("normalize", {}).get("mean", [0.485, 0.456, 0.406])
        std = aug_cfg.get("normalize", {}).get("std", [0.229, 0.224, 0.225])
        ops.append(T.Normalize(mean=mean, std=std))
        
        return T.Compose(ops)
    
    @staticmethod
    def get_default_config() -> Dict[str, Any]:
        """Get default augmentation configuration."""
        return {
            "augmentation": {
                "random_horizontal_flip": True,
                "random_vertical_flip": False,
                "random_rotation": 15,
                "gaussian_blur": False,
                "color_jitter": {
                    "brightness": 0.2,
                    "contrast": 0.2,
                    "saturation": 0.2,
                    "hue": 0
                },
                "random_affine": None,
                "normalize": {
                    "mean": [0.485, 0.456, 0.406],
                    "std": [0.229, 0.224, 0.225]
                }
            }
        }
