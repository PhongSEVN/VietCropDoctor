"""Dataset implementation for ResNet50 plant disease classification."""
import torch
from torch.utils.data import Dataset
from PIL import Image
import os
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import torchvision.transforms as T


class ResNetImageDataset(Dataset):
    """Image dataset for ResNet50."""
    
    def __init__(
        self,
        root_dir: str,
        config: Dict[str, Any],
        image_size: int = 224,
        train: bool = True,
        transform=None
    ):
        """
        Initialize ResNetImageDataset.
        
        Args:
            root_dir: Path to dataset root directory
            config: Configuration dictionary
            image_size: Target image size
            train: Whether in training mode
            transform: Optional custom transform
        """
        self.root_dir = Path(root_dir)
        self.config = config
        self.image_size = image_size
        self.train = train
        self.samples = []
        
        # Build augmentations
        if transform is None:
            self.transform = self._build_transforms(train, image_size, config)
        else:
            self.transform = transform
        
        # Load class information
        self.classes = sorted([d.name for d in self.root_dir.iterdir() if d.is_dir()])
        self.class_to_idx = {cls: idx for idx, cls in enumerate(self.classes)}
        
        # Load samples
        for cls in self.classes:
            cls_path = self.root_dir / cls
            for img_name in os.listdir(cls_path):
                if img_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):
                    self.samples.append((
                        cls_path / img_name,
                        self.class_to_idx[cls]
                    ))
        
        print(f"Loaded {len(self.samples)} images from {len(self.classes)} classes")
    
    def _build_transforms(self, train: bool, image_size: int, config: Dict) -> T.Compose:
        """Build augmentation pipeline."""
        aug_cfg = config.get("augmentation", {})
        
        ops = [T.Resize((image_size, image_size))]
        
        if train:
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
            
            # Gaussian blur
            if aug_cfg.get("gaussian_blur", False):
                ops.append(T.GaussianBlur(kernel_size=3, sigma=(0.1, 2.0)))
        
        # To tensor and normalize
        ops.append(T.ToTensor())
        mean = aug_cfg.get("normalize", {}).get("mean", [0.485, 0.456, 0.406])
        std = aug_cfg.get("normalize", {}).get("std", [0.229, 0.224, 0.225])
        ops.append(T.Normalize(mean=mean, std=std))
        
        return T.Compose(ops)
    
    def __len__(self) -> int:
        return len(self.samples)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        img_path, label = self.samples[idx]
        try:
            image = Image.open(img_path).convert('RGB')
        except Exception:
            image = Image.new('RGB', (224, 224), (0, 0, 0))
        if self.transform:
            image = self.transform(image)
        return image, label
    
    def get_class_names(self):
        """Get list of class names."""
        return self.classes
    
    def get_class_counts(self) -> Dict[str, int]:
        """Get count of samples per class."""
        counts = {cls: 0 for cls in self.classes}
        for _, label in self.samples:
            cls_name = self.classes[label]
            counts[cls_name] += 1
        return counts
