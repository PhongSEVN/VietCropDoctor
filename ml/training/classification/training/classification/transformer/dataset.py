"""Dataset implementation for Vision Transformer plant disease classification."""
import torch
from torch.utils.data import Dataset
from PIL import Image
import os
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from augment import AugmentParser


class TransformerImageDataset(Dataset):
    """Image dataset for Vision Transformer."""
    
    def __init__(
        self,
        root_dir: str,
        config: Dict[str, Any],
        image_size: int = 224,
        train: bool = True,
        transform=None
    ):
        """
        Initialize TransformerImageDataset.
        
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
            augment_parser = AugmentParser(config, image_size, train=train)
            self.transform = augment_parser.build_transforms()
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
