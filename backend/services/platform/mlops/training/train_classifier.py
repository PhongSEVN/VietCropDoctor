"""
Train a crop-disease classifier and log everything to MLflow.

Usage:
    python training/train_classifier.py --config training/configs/mobilenetv3_baseline.yaml
    python training/train_classifier.py --config training/configs/mobilenetv3_baseline.yaml \
        --data-dir /data/training --output-dir /data/models
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import mlflow
import mlflow.pytorch
import torch
import torch.nn as nn
import torchvision.transforms as T
import yaml
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, Subset, random_split
from torchvision.datasets import ImageFolder

# Ensure sibling modules resolve when running as a script from /workspace
sys.path.insert(0, str(Path(__file__).parent))
from build_model import build_model  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


# Config

@dataclass
class TrainConfig:
    arch: str = "mobilenetv3_large"
    num_classes: int = 25
    epochs: int = 50
    batch_size: int = 32
    lr: float = 0.001
    optimizer: str = "adam"
    image_size: int = 224
    augmentation: list = field(default_factory=list)
    early_stopping_patience: int = 7
    run_name: str = ""
    data_dir: str = "data/training"
    output_dir: str = "data/models"
    val_split: float = 0.2
    num_workers: int = 2

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TrainConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def override(self, **kwargs) -> "TrainConfig":
        for k, v in kwargs.items():
            if v is not None and hasattr(self, k):
                setattr(self, k, v)
        return self


# Transforms

def _build_transforms(config: TrainConfig):
    aug = config.augmentation
    size = config.image_size
    mean = [0.485, 0.456, 0.406]
    std  = [0.229, 0.224, 0.225]

    train_ops: list = [T.Resize((size, size))]
    if "random_flip" in aug:
        train_ops += [T.RandomHorizontalFlip(), T.RandomVerticalFlip()]
    if "random_rotation" in aug:
        train_ops.append(T.RandomRotation(15))
    if "color_jitter" in aug:
        train_ops.append(T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2, hue=0.05))
    train_ops += [T.ToTensor(), T.Normalize(mean, std)]

    train_tf = T.Compose(train_ops)
    val_tf   = T.Compose([T.Resize((size, size)), T.ToTensor(), T.Normalize(mean, std)])
    return train_tf, val_tf


# Mixup

def _mixup_batch(images: torch.Tensor, labels: torch.Tensor, alpha: float = 0.2):
    if alpha <= 0:
        return images, labels, labels, 1.0
    lam = float(torch.distributions.Beta(alpha, alpha).sample())
    idx = torch.randperm(images.size(0), device=images.device)
    mixed = lam * images + (1 - lam) * images[idx]
    return mixed, labels, labels[idx], lam


# Optimizer

def _build_optimizer(model: nn.Module, config: TrainConfig):
    name = config.optimizer.lower()
    if name == "adam":
        return torch.optim.Adam(model.parameters(), lr=config.lr)
    if name == "adamw":
        return torch.optim.AdamW(model.parameters(), lr=config.lr, weight_decay=1e-4)
    if name == "sgd":
        return torch.optim.SGD(model.parameters(), lr=config.lr, momentum=0.9, weight_decay=1e-4)
    raise ValueError(f"Unknown optimizer: {config.optimizer}")


# Train / eval loops

def _train_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    use_mixup: bool,
) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)

        if use_mixup:
            images, labels_a, labels_b, lam = _mixup_batch(images, labels)
            logits = model(images)
            loss = lam * criterion(logits, labels_a) + (1 - lam) * criterion(logits, labels_b)
            preds = logits.argmax(dim=1)
            correct += (lam * (preds == labels_a).float() + (1 - lam) * (preds == labels_b).float()).sum().item()
        else:
            logits = model(images)
            loss = criterion(logits, labels)
            preds = logits.argmax(dim=1)
            correct += (preds == labels).sum().item()

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)
        total += images.size(0)

    return total_loss / total, correct / total


@torch.no_grad()
def _eval_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, float, float]:
    model.eval()
    total_loss = 0.0
    all_preds: list[int] = []
    all_labels: list[int] = []

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        logits = model(images)
        loss = criterion(logits, labels)
        total_loss += loss.item() * images.size(0)
        all_preds.extend(logits.argmax(dim=1).cpu().tolist())
        all_labels.extend(labels.cpu().tolist())

    n = len(all_labels)
    acc = sum(p == l for p, l in zip(all_preds, all_labels)) / n
    f1  = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    return total_loss / n, acc, f1


# Main training entry point

def train(config: TrainConfig) -> str:
    """Train model and return the MLflow run_id."""
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Device: %s", device)

    # Data
    train_tf, val_tf = _build_transforms(config)

    data_path = Path(config.data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"data_dir not found: {data_path}")

    full_dataset = ImageFolder(data_path, transform=train_tf)
    detected_classes = len(full_dataset.classes)
    if detected_classes != config.num_classes:
        logger.warning(
            "Config num_classes=%d but dataset has %d classes — using %d",
            config.num_classes, detected_classes, detected_classes,
        )
        config.num_classes = detected_classes

    n_val   = max(1, int(len(full_dataset) * config.val_split))
    n_train = len(full_dataset) - n_val
    train_subset, val_subset = random_split(
        full_dataset, [n_train, n_val],
        generator=torch.Generator().manual_seed(42),
    )
    # Apply val transform to val subset without mutating the shared dataset
    val_subset.dataset = ImageFolder(data_path, transform=val_tf)  # type: ignore[attr-defined]

    train_loader = DataLoader(train_subset, batch_size=config.batch_size, shuffle=True,
                              num_workers=config.num_workers, pin_memory=device.type == "cuda")
    val_loader   = DataLoader(val_subset,   batch_size=config.batch_size, shuffle=False,
                              num_workers=config.num_workers, pin_memory=device.type == "cuda")

    logger.info("Dataset: %d train / %d val | %d classes", n_train, n_val, config.num_classes)

    # Model
    model = build_model(config).to(device)
    optimizer = _build_optimizer(model, config)
    criterion = nn.CrossEntropyLoss()
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs)

    use_mixup = "mixup" in config.augmentation
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    best_ckpt = output_dir / f"{config.arch}_best.pth"

    # MLflow run
    run_name = config.run_name or f"{config.arch}-{int(time.time())}"
    with mlflow.start_run(run_name=run_name) as run:
        mlflow.log_params({
            "arch":          config.arch,
            "num_classes":   config.num_classes,
            "epochs":        config.epochs,
            "batch_size":    config.batch_size,
            "lr":            config.lr,
            "optimizer":     config.optimizer,
            "image_size":    config.image_size,
            "augmentation":  ",".join(config.augmentation),
        })

        best_val_acc = 0.0
        patience_counter = 0
        best_model_state = None

        for epoch in range(1, config.epochs + 1):
            t0 = time.time()
            train_loss, train_acc = _train_epoch(model, train_loader, criterion, optimizer, device, use_mixup)
            val_loss,   val_acc, val_f1 = _eval_epoch(model, val_loader, criterion, device)
            scheduler.step()
            elapsed = time.time() - t0

            mlflow.log_metrics(
                {
                    "train_loss": round(train_loss, 4),
                    "train_acc":  round(train_acc, 4),
                    "val_loss":   round(val_loss, 4),
                    "val_acc":    round(val_acc, 4),
                    "val_f1":     round(val_f1, 4),
                },
                step=epoch,
            )
            logger.info(
                "Epoch %d/%d  train_loss=%.4f acc=%.3f  val_loss=%.4f acc=%.3f f1=%.3f  (%.1fs)",
                epoch, config.epochs, train_loss, train_acc, val_loss, val_acc, val_f1, elapsed,
            )

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                patience_counter = 0
                best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
                torch.save(
                    {
                        "model_state_dict": best_model_state,
                        "class_names": full_dataset.classes,
                        "num_classes": config.num_classes,
                        "arch": config.arch,
                        "val_acc": best_val_acc,
                    },
                    best_ckpt,
                )
            else:
                patience_counter += 1
                if patience_counter >= config.early_stopping_patience:
                    logger.info("Early stopping at epoch %d (patience=%d)", epoch, config.early_stopping_patience)
                    break

        # Load best weights before registering
        if best_model_state is not None:
            model.load_state_dict(best_model_state)

        mlflow.log_metric("best_val_acc", best_val_acc)
        mlflow.log_artifact(str(best_ckpt), artifact_path="checkpoints")

        mlflow.pytorch.log_model(
            model,
            artifact_path="model",
            registered_model_name="VietCropDoctor-Classifier",
        )

        run_id = run.info.run_id
        logger.info("MLflow run_id: %s  best_val_acc=%.4f", run_id, best_val_acc)
        return run_id


# CLI

def main() -> None:
    parser = argparse.ArgumentParser(description="Train VietCropDoctor classifier")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--data-dir",   default=None, help="Override config data_dir")
    parser.add_argument("--output-dir", default=None, help="Override config output_dir")
    parser.add_argument("--run-name",   default=None, help="Override MLflow run name")
    args = parser.parse_args()

    config = TrainConfig.from_yaml(args.config).override(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        run_name=args.run_name,
    )

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("VietCropDoctor")
    logger.info("MLflow tracking URI: %s", tracking_uri)

    run_id = train(config)
    print(f"run_id={run_id}")


if __name__ == "__main__":
    main()
