"""Prediction utilities for trained models."""
import sys
from pathlib import Path
import torch
import torch.nn.functional as F
from PIL import Image
import torchvision.transforms as T
from typing import Tuple, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cv.transformer.model import build_transformer_model, get_image_processor
from cv.transformer.augment import AugmentParser


class TransformerPredictor:
    """Predictor for Vision Transformer model."""
    
    def __init__(
        self,
        model_path: str,
        num_classes: int,
        class_names: List[str] = None,
        device: str = None
    ):
        """
        Initialize predictor.
        
        Args:
            model_path: Path to saved model weights
            num_classes: Number of classes
            class_names: List of class names
            device: Device to use (cuda/cpu)
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = build_transformer_model(num_classes=num_classes).to(self.device)
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval()
        
        self.class_names = class_names or [f"class_{i}" for i in range(num_classes)]
        self.num_classes = num_classes
        
        # Build preprocessing
        aug_cfg = AugmentParser.get_default_config()
        aug_parser = AugmentParser(aug_cfg, image_size=224, train=False)
        self.transform = aug_parser.build_transforms()
    
    def predict(self, image_path: str) -> Tuple[str, float, Dict]:
        """
        Predict disease class from image.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Tuple of (class_name, confidence, class_probabilities)
        """
        # Load and preprocess image
        image = Image.open(image_path).convert('RGB')
        image_tensor = self.transform(image).unsqueeze(0).to(self.device)
        
        # Predict
        with torch.no_grad():
            outputs = self.model(image_tensor)
            probabilities = F.softmax(outputs, dim=1)
            confidence, pred_idx = torch.max(probabilities, dim=1)
        
        pred_class = self.class_names[pred_idx.item()]
        confidence = confidence.item()
        
        # Get all probabilities
        class_probs = {
            cls: prob for cls, prob in zip(
                self.class_names,
                probabilities[0].cpu().tolist()
            )
        }
        
        return pred_class, confidence, class_probs


class ResNetPredictor:
    """Predictor for ResNet50 model."""
    
    def __init__(
        self,
        model_path: str,
        num_classes: int,
        class_names: List[str] = None,
        device: str = None
    ):
        """
        Initialize predictor.
        
        Args:
            model_path: Path to saved model weights
            num_classes: Number of classes
            class_names: List of class names
            device: Device to use (cuda/cpu)
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        
        from cv.Resnet50.model import build_resnet50_model
        self.model = build_resnet50_model(num_classes=num_classes).to(self.device)
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval()
        
        self.class_names = class_names or [f"class_{i}" for i in range(num_classes)]
        self.num_classes = num_classes
        
        # Build preprocessing
        mean = [0.485, 0.456, 0.406]
        std = [0.229, 0.224, 0.225]
        self.transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=mean, std=std)
        ])
    
    def predict(self, image_path: str) -> Tuple[str, float, Dict]:
        """
        Predict disease class from image.
        
        Args:
            image_path: Path to image file
            
        Returns:
            Tuple of (class_name, confidence, class_probabilities)
        """
        # Load and preprocess image
        image = Image.open(image_path).convert('RGB')
        image_tensor = self.transform(image).unsqueeze(0).to(self.device)
        
        # Predict
        with torch.no_grad():
            outputs = self.model(image_tensor)
            probabilities = F.softmax(outputs, dim=1)
            confidence, pred_idx = torch.max(probabilities, dim=1)
        
        pred_class = self.class_names[pred_idx.item()]
        confidence = confidence.item()
        
        # Get all probabilities
        class_probs = {
            cls: prob for cls, prob in zip(
                self.class_names,
                probabilities[0].cpu().tolist()
            )
        }
        
        return pred_class, confidence, class_probs
