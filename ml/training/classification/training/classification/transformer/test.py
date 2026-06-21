"""Test script for Vision Transformer."""
import sys
from pathlib import Path
import yaml
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from sklearn.metrics import classification_report, confusion_matrix
import numpy as np
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cv.transformer.dataset import TransformerImageDataset
from cv.transformer.model import build_transformer_model


def load_config() -> dict:
    """Load configuration."""
    config_path = PROJECT_ROOT / "configs" / "transformer_training_config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def plot_confusion_matrix(cm, class_names, save_path):
    """Plot confusion matrix."""
    fig, ax = plt.subplots(figsize=(max(10, len(class_names) * 0.6), max(8, len(class_names) * 0.5)))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    plt.colorbar(im, ax=ax)
    
    ax.set_xticks(range(len(class_names)))
    ax.set_yticks(range(len(class_names)))
    ax.set_xticklabels(class_names, rotation=45, ha='right', fontsize=8)
    ax.set_yticklabels(class_names, fontsize=8)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix — Test Set")
    
    # Add values in cells
    for i in range(len(class_names)):
        for j in range(len(class_names)):
            text = ax.text(j, i, cm[i, j], ha="center", va="center", color="black", fontsize=8)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()


@torch.no_grad()
def test(model, test_loader, device, class_names):
    """Test model."""
    model.eval()
    all_preds = []
    all_labels = []
    
    for images, labels in test_loader:
        images = images.to(device)
        labels = labels.to(device)
        
        outputs = model(images)
        _, preds = torch.max(outputs, 1)
        
        all_preds.extend(preds.cpu().tolist())
        all_labels.extend(labels.cpu().tolist())
    
    # Metrics
    accuracy = sum(p == l for p, l in zip(all_preds, all_labels)) / len(all_labels)
    
    print(f"\nTest Accuracy: {accuracy:.4f}")
    print("\nClassification Report:")
    print(classification_report(all_labels, all_preds, target_names=class_names))
    
    # Confusion matrix
    cm = confusion_matrix(all_labels, all_preds)
    print("\nConfusion Matrix:")
    print(cm)
    
    return cm, all_preds, all_labels


def main():
    """Main test function."""
    cfg = load_config()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}\n")
    
    # Paths
    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]
    models_dir = PROJECT_ROOT / cfg["output"].get("models_dir", "cv/results/transformer/models")
    results_dir = PROJECT_ROOT / cfg["output"].get("results_dir", "cv/results/transformer")
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Load dataset
    print("Loading test dataset...")
    test_ds = TransformerImageDataset(
        dataset_root / "test",
        cfg,
        image_size=cfg["dataset"]["image_size"],
        train=False
    )
    
    class_names = test_ds.get_class_names()
    print(f"Classes: {class_names}\n")
    
    test_loader = DataLoader(
        test_ds,
        batch_size=cfg["training"]["batch_size"],
        shuffle=False,
        num_workers=cfg["training"]["num_workers"],
        pin_memory=True
    )
    
    # Model
    print("Loading model...")
    num_classes = len(class_names)
    model = build_transformer_model(num_classes=num_classes).to(device)
    
    model_path = models_dir / "best_model.pth"
    if model_path.exists():
        model.load_state_dict(torch.load(model_path, map_location=device))
        print(f"Loaded model from {model_path}")
    else:
        print(f"Warning: Model not found at {model_path}")
    
    # Test
    cm, preds, labels = test(model, test_loader, device, class_names)
    
    # Save confusion matrix
    cm_path = results_dir / "confusion_matrix_test.png"
    plot_confusion_matrix(cm, class_names, cm_path)
    print(f"\nConfusion matrix saved to {cm_path}")


if __name__ == '__main__':
    main()