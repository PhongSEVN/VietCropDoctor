import sys
import csv
import os
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mlflow
import mlflow.pytorch
import torch
import torch.nn as nn
import torch.optim as optim
import yaml
from torch.utils.data import DataLoader
from tqdm import tqdm

_HERE = Path(__file__).parent
PROJECT_ROOT = _HERE.parent.parent.parent          # training/classification/
sys.path.insert(0, str(_HERE))                     # dataset.py, model.py
sys.path.insert(0, str(_HERE.parent))              # utils.py

from dataset import ResNetImageDataset
from model import build_resnet50_model
from utils import (
    EarlyStopping,
    compute_class_weights,
    run_test_evaluation,
    set_seed,
)

CONFIG_PATH = PROJECT_ROOT / "configs" / "resnet_training_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def train_one_epoch(model, train_loader, optimizer, criterion, device, desc="train") -> tuple:
    model.train()
    total_loss = correct = total = 0

    for batch_idx, (images, labels) in enumerate(tqdm(train_loader, desc=desc, leave=False), 1):
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item()
        _, preds = torch.max(outputs, 1)
        correct += (preds == labels).sum().item()
        total += labels.size(0)

    return total_loss / len(train_loader), correct / total


@torch.no_grad()
def evaluate(model, val_loader, criterion, device, desc="val") -> tuple:
    model.eval()
    total_loss = correct = total = 0
    all_preds, all_labels = [], []

    for batch_idx, (images, labels) in enumerate(tqdm(val_loader, desc=desc, leave=False), 1):
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        loss = criterion(outputs, labels)

        total_loss += loss.item()
        _, preds = torch.max(outputs, 1)
        correct += (preds == labels).sum().item()
        total += labels.size(0)
        all_preds.extend(preds.cpu().tolist())
        all_labels.extend(labels.cpu().tolist())

    return total_loss / len(val_loader), correct / total, all_preds, all_labels


def main():
    cfg = load_config()
    set_seed(cfg["training"]["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]
    results_dir = _HERE.parent / "results" / "resnet50"
    models_dir = results_dir / "models"
    results_dir.mkdir(parents=True, exist_ok=True)
    models_dir.mkdir(parents=True, exist_ok=True)

    train_ds = ResNetImageDataset(dataset_root / "train", cfg, image_size=cfg["dataset"]["image_size"], train=True)
    val_ds = ResNetImageDataset(dataset_root / "val", cfg, image_size=cfg["dataset"]["image_size"], train=False)
    test_ds = ResNetImageDataset(dataset_root / "test", cfg, image_size=cfg["dataset"]["image_size"], train=False)

    num_classes = len(train_ds.classes)
    print(f"Classes ({num_classes}): {train_ds.classes}")

    batch_size = cfg["training"]["batch_size"]
    num_workers = cfg["training"]["num_workers"]
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers, pin_memory=True, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=True)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=True)

    model = build_resnet50_model(
        num_classes=num_classes,
        dropout=cfg["model"].get("dropout", 0.3),
        pretrained=cfg["model"].get("pretrained", True),
        frozen_backbone=True,
    ).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Parameters: {total_params:,} total, {trainable_params:,} trainable")

    epochs = cfg["training"]["epochs"]
    optimizer = optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=cfg["optimizer"]["lr"],
        weight_decay=cfg["optimizer"]["weight_decay"],
    )
    warmup_epochs = cfg["scheduler"].get("warmup_epochs", 3)
    warmup_scheduler = torch.optim.lr_scheduler.LinearLR(
        optimizer,
        start_factor=0.01,
        end_factor=1.0,
        total_iters=warmup_epochs,
    )
    cosine_scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer,
        T_max=max(1, epochs - warmup_epochs),
        eta_min=cfg["scheduler"].get("min_lr", 1e-6),
    )
    scheduler = torch.optim.lr_scheduler.SequentialLR(
        optimizer,
        schedulers=[warmup_scheduler, cosine_scheduler],
        milestones=[warmup_epochs],
    )
    imb_cfg = cfg.get("imbalance", {})
    imb_strategy = imb_cfg.get("strategy", "balanced")
    if imb_strategy == "none":
        criterion = nn.CrossEntropyLoss()
    else:
        class_weights = compute_class_weights(
            train_ds.samples, num_classes, device,
            strategy=imb_strategy, beta=imb_cfg.get("beta", 0.999),
        )
        criterion = nn.CrossEntropyLoss(weight=class_weights)
    early_stop = EarlyStopping(patience=cfg["output"]["early_stopping_patience"])

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    mlflow.set_experiment("plant-disease-classification")
    mlflow.start_run(run_name="resnet50")
    mlflow.set_tag("model_name", "resnet50")
    mlflow.set_tags({
        "stage": os.getenv("EXP_STAGE", "baseline"),
        "imbalance_strategy": imb_strategy,
        "augment_min_samples": cfg["augmentation"].get("min_samples"),
        "seed": cfg["training"].get("seed"),
        "tta": cfg.get("eval", {}).get("tta", False),
    })
    try:
        mlflow.log_params({
            "backbone": "resnet50",
            "epochs": epochs,
            "batch_size": batch_size,
            "image_size": cfg["dataset"]["image_size"],
            "lr": cfg["optimizer"]["lr"],
            "weight_decay": cfg["optimizer"]["weight_decay"],
            "dropout": cfg["model"].get("dropout", 0.3),
            "num_classes": num_classes,
        })

        start_epoch = 1
        log = []
        best_val_loss = float("inf")
        checkpoint_path = models_dir / "last_checkpoint.pth"

        if checkpoint_path.exists():
            print(f"Resuming from checkpoint: {checkpoint_path}")
            checkpoint = torch.load(checkpoint_path, map_location=device)
            model.load_state_dict(checkpoint["model_state_dict"])
            optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
            scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
            start_epoch = checkpoint["epoch"] + 1
            best_val_loss = checkpoint.get("best_val_loss", float("inf"))
            early_stop.best_loss = checkpoint.get("early_stop_best_loss", float("inf"))
            early_stop.counter = checkpoint.get("early_stop_counter", 0)
            log = checkpoint.get("training_log", [])
            print(f"Resumed from epoch {checkpoint['epoch']}, best_val_loss={best_val_loss:.4f}\n")

        print("Starting training...\n")
        for epoch in range(start_epoch, epochs + 1):
            unfreeze_epoch = cfg["training"].get("unfreeze_epoch", epochs + 1)
            if epoch == unfreeze_epoch:
                print(f"\n[Epoch {epoch}] Unfreezing backbone")
                model.unfreeze_backbone()
                for param_group in optimizer.param_groups:
                    param_group["lr"] = cfg["optimizer"]["lr"] * 0.1

            train_loss, train_acc = train_one_epoch(
                model, train_loader, optimizer, criterion, device,
                desc=f"Epoch {epoch}/{epochs} [train]",
            )
            val_loss, val_acc, _, _ = evaluate(
                model, val_loader, criterion, device,
                desc=f"Epoch {epoch}/{epochs} [val]",
            )
            scheduler.step()

            log.append({
                "epoch": epoch, "train_loss": train_loss, "train_acc": train_acc,
                "val_loss": val_loss, "val_acc": val_acc,
                "lr": optimizer.param_groups[0]["lr"],
            })
            print(
                f"Epoch {epoch}/{epochs} | "
                f"Train Loss: {train_loss:.4f}, Acc: {train_acc:.4f} | "
                f"Val Loss: {val_loss:.4f}, Acc: {val_acc:.4f} | "
                f"LR: {optimizer.param_groups[0]['lr']:.2e}"
            )
            mlflow.log_metrics({
                "train_loss": train_loss, "train_acc": train_acc,
                "val_loss": val_loss, "val_acc": val_acc,
                "lr": optimizer.param_groups[0]["lr"],
            }, step=epoch)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                torch.save({
                    "epoch": epoch,
                    "backbone": "resnet50",
                    "num_classes": num_classes,
                    "class_names": train_ds.classes,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "val_loss": val_loss,
                    "val_acc": val_acc,
                }, models_dir / "best_model.pth")
                print("Saved best model")

            torch.save(model.state_dict(), models_dir / "last_model.pth")
            torch.save({
                "epoch": epoch,
                "backbone": "resnet50",
                "num_classes": num_classes,
                "class_names": train_ds.classes,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "scheduler_state_dict": scheduler.state_dict(),
                "best_val_loss": best_val_loss,
                "early_stop_best_loss": early_stop.best_loss,
                "early_stop_counter": early_stop.counter,
                "training_log": log,
                "config": cfg,
            }, checkpoint_path)

            if early_stop(val_loss):
                print(f"\nEarly stopping at epoch {epoch}")
                break

        log_file = results_dir / f"training_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(log_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=log[0].keys())
            writer.writeheader()
            writer.writerows(log)

        ep = [r["epoch"] for r in log]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
        ax1.plot(ep, [r["train_loss"] for r in log], label="train")
        ax1.plot(ep, [r["val_loss"] for r in log], label="val")
        ax1.set_title("Loss"); ax1.set_xlabel("Epoch"); ax1.legend()
        ax2.plot(ep, [r["train_acc"] for r in log], label="train")
        ax2.plot(ep, [r["val_acc"] for r in log], label="val")
        ax2.set_title("Accuracy"); ax2.set_xlabel("Epoch"); ax2.legend()
        plt.suptitle("ResNet50 — training curves")
        plt.tight_layout()
        plt.savefig(results_dir / "training_curves.png", dpi=150)
        plt.close()

        torch.save(model.state_dict(), models_dir / "final_model.pth")

        ckpt = torch.load(models_dir / "best_model.pth", map_location=device)
        model.load_state_dict(ckpt["model_state_dict"])
        test_acc, test_macro_f1, test_weighted_f1 = run_test_evaluation(
            model, test_loader, criterion, device, train_ds.classes, results_dir,
            tta=cfg.get("eval", {}).get("tta", False))

        mlflow.log_metrics({
            "test_acc": test_acc,
            "test_macro_f1": test_macro_f1,
            "test_weighted_f1": test_weighted_f1,
        })
        mlflow.log_artifact(str(results_dir / "confusion_matrix.png"))
        mlflow.log_artifact(str(results_dir / "training_curves.png"))
        mlflow.log_artifact(str(results_dir / "per_class_f1.json"))
        mlflow.set_tag(
            "mlflow.note.content",
            f"resnet50 | imbalance={imb_strategy} | "
            f"test_macro_f1={test_macro_f1:.4f} test_acc={test_acc:.4f}",
        )
        run_id = mlflow.active_run().info.run_id
        # Log the trained weights as a plain artifact. This uses the stable
        # artifact API and works regardless of the MLflow server version (the
        # 3.x-only logged-models endpoint is not required here).
        try:
            mlflow.log_artifact(str(models_dir / "best_model.pth"), artifact_path="model")
        except Exception as exc:
            print(f"[WARN] MLflow checkpoint artifact logging skipped: {exc}")
        # Best-effort native model logging + registry. Needs the MLflow client and
        # server versions to match; skipped quietly on a version mismatch.
        try:
            mlflow.pytorch.log_model(model, "model_pytorch")
            mlflow.register_model(f"runs:/{run_id}/model_pytorch", "VietCropDoctor-resnet50")
        except Exception as exc:
            print(f"[WARN] MLflow native model logging/registration skipped (version mismatch?): {exc}")
    finally:
        mlflow.end_run()


if __name__ == "__main__":
    main()
