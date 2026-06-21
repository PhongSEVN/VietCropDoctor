"""Shared training utilities for all classification models.

Class-imbalance helpers (compute_class_weights, FocalLoss, make_weighted_sampler)
live in imbalance.py and are re-exported via this package's __init__.
"""
import json
import random
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import classification_report
from sklearn.metrics import confusion_matrix as sk_confusion_matrix
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader

from .tta import tta_probabilities


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


class EarlyStopping:
    def __init__(self, patience: int = 10, delta: float = 0.0):
        self.patience = patience
        self.delta = delta
        self.counter = 0
        self.best_loss = float("inf")

    def __call__(self, val_loss: float) -> bool:
        if val_loss < self.best_loss - self.delta:
            self.best_loss = val_loss
            self.counter = 0
            return False
        self.counter += 1
        return self.counter >= self.patience


def plot_confusion_matrix(cm: np.ndarray, class_names: list, save_path: Path) -> None:
    n = len(class_names)
    fig, ax = plt.subplots(figsize=(max(10, n * 0.6), max(8, n * 0.5)))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    plt.colorbar(im, ax=ax)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(class_names, rotation=90, fontsize=7)
    ax.set_yticklabels(class_names, fontsize=7)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix — Test Set")
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close()


@torch.no_grad()
def run_test_evaluation(
    model: nn.Module,
    test_loader: DataLoader,
    criterion: nn.Module,
    device,
    class_names: list,
    results_dir: Path,
    tta: bool = False,
) -> tuple[float, float, float]:
    """Evaluate on the test set, print the report, save the confusion matrix.

    Returns (test_acc, macro_f1, weighted_f1). macro_f1 is the unweighted mean of
    per-class F1 — the fair metric to compare models on an imbalanced dataset, since
    it gives every class equal say regardless of how many images it has.

    When ``tta`` is True, predictions are averaged over Test-Time Augmentation views
    (see tta.py). Default False keeps the plain single-forward behaviour unchanged.
    """
    model.eval()
    total_loss = correct = total = 0
    all_preds, all_labels = [], []

    for imgs, labels in test_loader:
        imgs, labels = imgs.to(device), labels.to(device)
        out = model(imgs)
        loss = criterion(out, labels)
        total_loss += loss.item() * len(labels)
        # TTA only affects the predicted class (averaged softmax); loss stays on
        # the plain forward output so it remains comparable across runs.
        probs = tta_probabilities(model, imgs, enabled=True) if tta else out
        preds = probs.argmax(1)
        correct += (preds == labels).sum().item()
        total += len(labels)
        all_preds.extend(preds.cpu().tolist())
        all_labels.extend(labels.cpu().tolist())

    test_acc = correct / total
    macro_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0)
    weighted_f1 = f1_score(all_labels, all_preds, average="weighted", zero_division=0)
    print(f"\nTest accuracy : {test_acc:.4f}")
    print(f"Macro F1      : {macro_f1:.4f}  (unweighted mean over classes)")
    print(f"Weighted F1   : {weighted_f1:.4f}")
    print("\nClassification Report:")
    print(classification_report(all_labels, all_preds, target_names=class_names, digits=4))

    cm = sk_confusion_matrix(all_labels, all_preds)
    plot_confusion_matrix(cm, class_names, results_dir / "confusion_matrix.png")
    print(f"Saved confusion matrix: {results_dir / 'confusion_matrix.png'}")

    # Per-class F1 — surfaces which disease classes (often the rare ones) the
    # model is weakest on. Saved as an artifact; does NOT change the return value.
    per_class_scores = f1_score(
        all_labels, all_preds, average=None, zero_division=0,
        labels=list(range(len(class_names))),
    )
    per_class_f1 = {name: round(float(score), 4) for name, score in zip(class_names, per_class_scores)}
    print("\nPer-class F1 (weakest first):")
    for name, score in sorted(per_class_f1.items(), key=lambda kv: kv[1]):
        print(f"  {name:<40} {score:.4f}")
    per_class_path = results_dir / "per_class_f1.json"
    per_class_path.write_text(json.dumps(per_class_f1, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved per-class F1: {per_class_path}")

    return test_acc, macro_f1, weighted_f1
