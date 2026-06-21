"""Model comparison script for Vision Transformer vs ResNet50."""
import sys
from pathlib import Path
import yaml
import torch
from torch.utils.data import DataLoader
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cv.transformer.dataset import TransformerImageDataset
from cv.transformer.model import build_transformer_model
from cv.Resnet50.dataset import ResNetImageDataset
from cv.Resnet50.model import build_resnet50_model


def load_config() -> dict:
    """Load configuration."""
    config_path = PROJECT_ROOT / "configs" / "train_config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


@torch.no_grad()
def evaluate_model(model, test_loader, device, model_name: str):
    """Evaluate model on test set."""
    model.eval()
    correct = 0
    total = 0
    
    for images, labels in test_loader:
        images = images.to(device)
        labels = labels.to(device)
        
        outputs = model(images)
        _, preds = torch.max(outputs, 1)
        
        correct += (preds == labels).sum().item()
        total += labels.size(0)
    
    accuracy = correct / total
    return accuracy


def main():
    """Main comparison function."""
    cfg = load_config()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}\n")
    
    # Paths
    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]
    results_dir = PROJECT_ROOT / "cv" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    # Load test dataset
    print("Loading test dataset...")
    test_ds = TransformerImageDataset(
        dataset_root / "test",
        cfg,
        image_size=cfg["dataset"]["image_size"],
        train=False
    )
    
    class_names = test_ds.get_class_names()
    num_classes = len(class_names)
    print(f"Classes: {class_names}")
    print(f"Test samples: {len(test_ds)}\n")
    
    test_loader = DataLoader(
        test_ds,
        batch_size=cfg["training"]["batch_size"],
        shuffle=False,
        num_workers=cfg["training"]["num_workers"],
        pin_memory=True
    )
    
    # Load models
    print("=" * 60)
    print("Vision Transformer vs ResNet50 Comparison")
    print("=" * 60 + "\n")
    
    models_info = {
        'Vision Transformer': {
            'path': PROJECT_ROOT / "cv" / "transformer" / "models" / "best_model.pth",
            'builder': build_transformer_model,
            'params': {}
        },
        'ResNet50': {
            'path': PROJECT_ROOT / "cv" / "Resnet50" / "models" / "best_model.pth",
            'builder': build_resnet50_model,
            'params': {}
        }
    }
    
    results = {}
    
    for model_name, info in models_info.items():
        print(f"Evaluating {model_name}...")
        
        if not info['path'].exists():
            print(f"  WARNING: Model not found at {info['path']}")
            results[model_name] = {'accuracy': 0, 'exists': False}
            continue
        
        # Build and load model
        model = info['builder'](num_classes=num_classes, **info['params']).to(device)
        model.load_state_dict(torch.load(info['path'], map_location=device))
        
        # Count parameters
        total_params = sum(p.numel() for p in model.parameters())
        
        # Evaluate
        accuracy = evaluate_model(model, test_loader, device, model_name)
        
        results[model_name] = {
            'accuracy': accuracy,
            'total_params': total_params,
            'exists': True
        }
        
        print(f"  Accuracy: {accuracy:.4f}")
        print(f"  Parameters: {total_params:,}\n")
    
    # Create comparison table
    print("\n" + "=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60 + "\n")
    
    comparison_data = []
    for model_name, metrics in results.items():
        if metrics['exists']:
            comparison_data.append({
                'Model': model_name,
                'Test Accuracy': f"{metrics['accuracy']:.4f}",
                'Parameters': f"{metrics['total_params']:,}"
            })
    
    if comparison_data:
        df = pd.DataFrame(comparison_data)
        print(df.to_string(index=False))
        
        # Save comparison
        csv_file = results_dir / f"model_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(csv_file, index=False)
        print(f"\nComparison saved to {csv_file}")
        
        # Plot results
        if len(comparison_data) > 1:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
            
            # Accuracy comparison
            models = [d['Model'] for d in comparison_data]
            accuracies = [float(d['Test Accuracy']) for d in comparison_data]
            ax1.bar(models, accuracies, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
            ax1.set_ylabel('Accuracy')
            ax1.set_title('Model Accuracy Comparison (Test Set)')
            ax1.set_ylim([0, 1])
            for i, v in enumerate(accuracies):
                ax1.text(i, v + 0.02, f'{v:.4f}', ha='center')
            
            # Parameters comparison
            params = [float(d['Parameters'].replace(',', '')) for d in comparison_data]
            ax2.bar(models, params, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
            ax2.set_ylabel('Number of Parameters')
            ax2.set_title('Model Size Comparison')
            ax2.ticklabel_format(style='plain', axis='y')
            for i, v in enumerate(params):
                ax2.text(i, v + max(params)*0.02, f'{int(v):,}', ha='center', fontsize=9)
            
            plt.tight_layout()
            plot_file = results_dir / f"model_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(plot_file, dpi=150, bbox_inches='tight')
            print(f"Plot saved to {plot_file}")
            plt.close()
    else:
        print("No valid models found for comparison")
    
    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
