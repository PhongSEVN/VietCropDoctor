import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import csv
import yaml
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from tqdm import tqdm

from cv.dataset import PlantDiseaseDataset, get_transforms
from cv.model import build_model, freeze_backbone

CONFIG_PATH = PROJECT_ROOT / "configs" / "train_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def train_one_epoch(model, loader, optimizer, criterion, device) -> tuple[float, float]:
    model.train()
    total_loss = correct = total = 0
    for imgs, labels in tqdm(loader, leave=False):
        imgs, labels = imgs.to(device), labels.to(device)
        optimizer.zero_grad()
        out = model(imgs)
        loss = criterion(out, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(labels)
        correct += (out.argmax(1) == labels).sum().item()
        total += len(labels)
    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(model, loader, device) -> dict:
    model.eval()
    all_preds, all_labels = [], []
    for imgs, labels in loader:
        imgs = imgs.to(device)
        preds = model(imgs).argmax(1).cpu()
        all_preds.extend(preds.tolist())
        all_labels.extend(labels.tolist())
    return {
        "acc": accuracy_score(all_labels, all_preds),
        "precision": precision_score(all_labels, all_preds, average="macro", zero_division=0),
        "recall": recall_score(all_labels, all_preds, average="macro", zero_division=0),
        "f1": f1_score(all_labels, all_preds, average="macro", zero_division=0),
    }


def main():
    cfg = load_config()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]
    image_size = cfg["dataset"]["image_size"]
    batch_size = cfg["training"]["batch_size"]
    num_workers = cfg["training"]["num_workers"]
    epochs = cfg["compare"]["epochs"]
    lr = cfg["compare"]["lr"]
    dropout = cfg["model"]["dropout"]

    results_dir = PROJECT_ROOT / "cv" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    train_ds = PlantDiseaseDataset(dataset_root / "train", get_transforms(image_size, cfg, train=True))
    val_ds = PlantDiseaseDataset(dataset_root / "val", get_transforms(image_size, cfg, train=False))
    num_classes = len(train_ds.classes)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=True)

    backbones = ["efficientnet_b0", "resnet50", "mobilenet_v3_large"]
    summary = []

    for backbone in backbones:
        print(f"\n{'='*55}\n  {backbone}\n{'='*55}")
        model = build_model(backbone, num_classes, pretrained=True, dropout=dropout).to(device)
        freeze_backbone(model, backbone)

        optimizer = torch.optim.Adam(
            filter(lambda p: p.requires_grad, model.parameters()), lr=lr
        )
        criterion = nn.CrossEntropyLoss()

        for epoch in range(1, epochs + 1):
            train_loss, train_acc = train_one_epoch(model, train_loader, optimizer, criterion, device)
            metrics = evaluate(model, val_loader, device)
            print(
                f"Epoch {epoch:02d}/{epochs} | loss={train_loss:.4f} acc={train_acc:.4f} "
                f"| val_acc={metrics['acc']:.4f} f1={metrics['f1']:.4f}"
            )

        metrics = evaluate(model, val_loader, device)
        summary.append({"model": backbone, **metrics})
        print(f"\n  Final → acc={metrics['acc']:.4f} prec={metrics['precision']:.4f} rec={metrics['recall']:.4f} f1={metrics['f1']:.4f}")

    csv_path = results_dir / "model_comparison.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "acc", "precision", "recall", "f1"])
        writer.writeheader()
        writer.writerows(summary)
    print(f"\nĐã lưu: {csv_path}")

    names = [r["model"] for r in summary]
    accs = [r["acc"] for r in summary]
    f1s = [r["f1"] for r in summary]
    x = list(range(len(names)))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar([i - 0.2 for i in x], accs, width=0.38, label="Accuracy", color="#4CAF50")
    ax.bar([i + 0.2 for i in x], f1s, width=0.38, label="F1 macro", color="#2196F3")
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Score")
    ax.set_title("Model Comparison — val set (10 epochs, frozen backbone)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(results_dir / "comparison.png", dpi=150)
    plt.close()
    print(f"Đã lưu: {results_dir / 'comparison.png'}")

    best = max(summary, key=lambda r: r["acc"])
    print(f"\nModel tốt nhất: {best['model']}  val_acc={best['acc']:.4f}  f1={best['f1']:.4f}")


if __name__ == "__main__":
    main()
