"""
cv/compare.py
So sánh EfficientNet-B0 (đã train) vs YOLOv8-Classification trên test set.

Output:
    cv/results/compare_b0_yolo.csv      ← metrics từng class + tổng
    cv/results/compare_b0_yolo.png      ← bar chart so sánh
    cv/results/compare_confusion.png    ← confusion matrix song song
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import torch
import yaml
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from PIL import Image
from tqdm import tqdm
from sklearn.metrics import (
    accuracy_score, classification_report,
    confusion_matrix, ConfusionMatrixDisplay,
)

from cv.dataset import PlantDiseaseDataset, get_transforms
from cv.model import build_model

with open(PROJECT_ROOT / "configs" / "train_config.yaml") as f:
    cfg = yaml.safe_load(f)

TEST_DIR   = PROJECT_ROOT / cfg["dataset"]["test"]
IMAGE_SIZE = cfg["dataset"]["image_size"]
BATCH_SIZE = cfg["training"]["batch_size"]

B0_CKPT    = PROJECT_ROOT / "cv" / "models" / "best_model.pth"
YOLO_CKPT  = PROJECT_ROOT / "Yolo" / "runs" / "train" / "weights" / "best.pt"

RESULTS_DIR = PROJECT_ROOT / "cv" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def run_efficientnet(class_names: list[str]) -> tuple[list, list, float]:
    """Chạy inference B0 trên toàn bộ test set. Trả về (y_true, y_pred, ms_per_img)."""
    if not B0_CKPT.exists():
        raise FileNotFoundError(f"B0 checkpoint không tồn tại: {B0_CKPT}")

    ckpt  = torch.load(B0_CKPT, map_location=DEVICE)
    model = build_model(ckpt["backbone"], ckpt["num_classes"], pretrained=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval().to(DEVICE)

    # Đảm bảo thứ tự class khớp với checkpoint
    ckpt_classes = ckpt["class_names"]
    transform    = get_transforms(IMAGE_SIZE, cfg, train=False)
    dataset      = PlantDiseaseDataset(TEST_DIR, transform=transform)

    loader = torch.utils.data.DataLoader(
        dataset, batch_size=BATCH_SIZE, shuffle=False,
        num_workers=0, pin_memory=DEVICE.type == "cuda",
    )

    y_true, y_pred = [], []
    t0 = time.perf_counter()

    with torch.no_grad():
        for images, labels in tqdm(loader, desc="[B0] Inference", ncols=80):
            images = images.to(DEVICE)
            logits = model(images)
            preds  = logits.argmax(dim=1).cpu().tolist()
            y_pred.extend(preds)
            y_true.extend(labels.tolist())

    elapsed     = time.perf_counter() - t0
    ms_per_img  = elapsed / len(dataset) * 1000

    # Chuyển idx → class_name, dùng class_names từ dataset (đã sorted)
    return y_true, y_pred, ms_per_img, dataset.classes


def run_yolo(class_names: list[str]) -> tuple[list, list, float]:
    """Chạy inference YOLO trên toàn bộ test set. Trả về (y_true, y_pred, ms_per_img)."""
    if not YOLO_CKPT.exists():
        raise FileNotFoundError(
            f"YOLO checkpoint không tồn tại: {YOLO_CKPT}\n"
            f"Hãy chạy Yolo/train_yolo.py trước."
        )

    from ultralytics import YOLO
    model = YOLO(YOLO_CKPT)

    yolo_classes = model.names

    y_true, y_pred = [], []
    all_img_paths: list[tuple[Path, int]] = []

    for idx, cls in enumerate(class_names):
        cls_dir = TEST_DIR / cls
        for p in cls_dir.rglob("*"):
            if p.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                all_img_paths.append((p, idx))

    t0 = time.perf_counter()

    # YOLO predict từng ảnh (batch predict để tối ưu tốc độ)
    img_paths = [str(p) for p, _ in all_img_paths]
    results   = model.predict(
        source  = img_paths,
        imgsz   = IMAGE_SIZE,
        batch   = BATCH_SIZE,
        verbose = False,
        stream  = True,   # generator để tiết kiệm RAM
    )

    pred_labels = []
    for r in tqdm(results, total=len(all_img_paths), desc="[YOLO] Inference", ncols=80):
        top1_name = yolo_classes[r.probs.top1]
        # Map YOLO class name về index trong class_names list (sorted)
        pred_idx  = class_names.index(top1_name) if top1_name in class_names else -1
        pred_labels.append(pred_idx)

    elapsed    = time.perf_counter() - t0
    ms_per_img = elapsed / len(all_img_paths) * 1000

    y_true = [lbl for _, lbl in all_img_paths]
    y_pred = pred_labels
    return y_true, y_pred, ms_per_img


def compute_metrics(y_true, y_pred, class_names):
    """Trả về dict metrics tổng + per-class."""
    report = classification_report(
        y_true, y_pred,
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )
    return report


def print_comparison(b0_report, yolo_report, b0_ms, yolo_ms, class_names):
    """In bảng so sánh tổng hợp ra console."""
    print("\n" + "=" * 75)
    print(f"{'CLASS':<35} {'B0-F1':>8} {'YOLO-F1':>9} {'DIFF':>8}")
    print("=" * 75)

    for cls in class_names:
        b0_f1   = b0_report.get(cls, {}).get("f1-score", 0)
        yolo_f1 = yolo_report.get(cls, {}).get("f1-score", 0)
        diff    = yolo_f1 - b0_f1
        sign    = "+" if diff > 0 else ""
        print(f"  {cls:<33} {b0_f1:>8.4f} {yolo_f1:>9.4f} {sign}{diff:>7.4f}")

    print("=" * 75)
    b0_acc   = b0_report["accuracy"]
    yolo_acc = yolo_report["accuracy"]
    b0_mf1   = b0_report["macro avg"]["f1-score"]
    yolo_mf1 = yolo_report["macro avg"]["f1-score"]

    print(f"\n  {'Metric':<20} {'EfficientNet-B0':>16} {'YOLOv8-cls':>12}")
    print(f"  {'-'*20} {'-'*16} {'-'*12}")
    print(f"  {'Accuracy':<20} {b0_acc:>16.4f} {yolo_acc:>12.4f}")
    print(f"  {'Macro F1':<20} {b0_mf1:>16.4f} {yolo_mf1:>12.4f}")
    print(f"  {'Speed (ms/img)':<20} {b0_ms:>16.2f} {yolo_ms:>12.2f}")
    winner = "EfficientNet-B0" if b0_acc > yolo_acc else "YOLOv8-cls"
    print(f"\n  Mô hình tốt hơn (accuracy): {winner}")


def plot_comparison(b0_report, yolo_report, b0_ms, yolo_ms, class_names):
    """Vẽ 2 biểu đồ so sánh và lưu file."""
    fig = plt.figure(figsize=(18, 10))
    gs  = gridspec.GridSpec(1, 3, figure=fig, wspace=0.4)

    ax1 = fig.add_subplot(gs[0, :2])
    b0_f1s   = [b0_report.get(c, {}).get("f1-score", 0)   for c in class_names]
    yolo_f1s = [yolo_report.get(c, {}).get("f1-score", 0) for c in class_names]

    x   = np.arange(len(class_names))
    w   = 0.35
    ax1.bar(x - w/2, b0_f1s,   w, label="EfficientNet-B0", color="#4C9BE8", alpha=0.85)
    ax1.bar(x + w/2, yolo_f1s, w, label="YOLOv8-cls",      color="#E8834C", alpha=0.85)

    ax1.set_xticks(x)
    ax1.set_xticklabels(class_names, rotation=45, ha="right", fontsize=8)
    ax1.set_ylabel("F1-Score")
    ax1.set_title("F1-Score theo từng class", fontweight="bold")
    ax1.set_ylim(0, 1.05)
    ax1.yaxis.grid(True, linestyle="--", alpha=0.5)
    ax1.legend()

    ax2 = fig.add_subplot(gs[0, 2])
    metrics   = ["Accuracy", "Macro F1", "Macro Prec.", "Macro Rec."]
    b0_vals   = [
        b0_report["accuracy"],
        b0_report["macro avg"]["f1-score"],
        b0_report["macro avg"]["precision"],
        b0_report["macro avg"]["recall"],
    ]
    yolo_vals = [
        yolo_report["accuracy"],
        yolo_report["macro avg"]["f1-score"],
        yolo_report["macro avg"]["precision"],
        yolo_report["macro avg"]["recall"],
    ]

    x2 = np.arange(len(metrics))
    ax2.bar(x2 - 0.2, b0_vals,   0.35, label="EfficientNet-B0", color="#4C9BE8", alpha=0.85)
    ax2.bar(x2 + 0.2, yolo_vals, 0.35, label="YOLOv8-cls",      color="#E8834C", alpha=0.85)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(metrics, fontsize=9)
    ax2.set_title("Tổng hợp metrics", fontweight="bold")
    ax2.set_ylim(0, 1.15)
    ax2.yaxis.grid(True, linestyle="--", alpha=0.5)

    for bars in [ax2.containers[0], ax2.containers[1]]:
        ax2.bar_label(bars, fmt="%.3f", fontsize=8, padding=2)

    ax2.legend()

    ax2.text(
        0.5, -0.18,
        f"Speed — B0: {b0_ms:.1f} ms/img  |  YOLO: {yolo_ms:.1f} ms/img",
        ha="center", transform=ax2.transAxes, fontsize=8, color="gray",
    )

    plt.suptitle("So sánh EfficientNet-B0 vs YOLOv8-Classification",
                 fontsize=14, fontweight="bold")
    out = RESULTS_DIR / "compare_b0_yolo.png"
    plt.savefig(out, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"\n  → Biểu đồ so sánh: {out}")


def plot_confusion_matrices(b0_true, b0_pred, yolo_true, yolo_pred, class_names):
    """Vẽ 2 confusion matrix song song."""
    fig, axes = plt.subplots(1, 2, figsize=(24, 10))

    for ax, y_true, y_pred, title in [
        (axes[0], b0_true,   b0_pred,   "EfficientNet-B0"),
        (axes[1], yolo_true, yolo_pred, "YOLOv8-cls"),
    ]:
        cm = confusion_matrix(y_true, y_pred)
        disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=class_names)
        disp.plot(ax=ax, colorbar=False, xticks_rotation=45)
        ax.set_title(title, fontsize=13, fontweight="bold")
        ax.tick_params(axis="x", labelsize=7)
        ax.tick_params(axis="y", labelsize=7)

    plt.suptitle("Confusion Matrix — B0 vs YOLO", fontsize=14, fontweight="bold")
    plt.tight_layout()
    out = RESULTS_DIR / "compare_confusion.png"
    plt.savefig(out, bbox_inches="tight", dpi=120)
    plt.close()
    print(f"  → Confusion matrix: {out}")


def save_csv(b0_report, yolo_report, b0_ms, yolo_ms, class_names):
    import csv
    out = RESULTS_DIR / "compare_b0_yolo.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["class", "b0_precision", "b0_recall", "b0_f1",
                                  "yolo_precision", "yolo_recall", "yolo_f1", "diff_f1"])
        for cls in class_names:
            b0   = b0_report.get(cls, {})
            yolo = yolo_report.get(cls, {})
            writer.writerow([
                cls,
                f"{b0.get('precision',0):.4f}",
                f"{b0.get('recall',0):.4f}",
                f"{b0.get('f1-score',0):.4f}",
                f"{yolo.get('precision',0):.4f}",
                f"{yolo.get('recall',0):.4f}",
                f"{yolo.get('f1-score',0):.4f}",
                f"{yolo.get('f1-score',0) - b0.get('f1-score',0):.4f}",
            ])
        for key in ["accuracy", "macro avg", "weighted avg"]:
            b0_val   = b0_report.get(key, {})
            yolo_val = yolo_report.get(key, {})
            if isinstance(b0_val, float):
                writer.writerow([key, "", "", f"{b0_val:.4f}", "", "", f"{yolo_val:.4f}", ""])
            else:
                writer.writerow([
                    key,
                    f"{b0_val.get('precision',0):.4f}",
                    f"{b0_val.get('recall',0):.4f}",
                    f"{b0_val.get('f1-score',0):.4f}",
                    f"{yolo_val.get('precision',0):.4f}",
                    f"{yolo_val.get('recall',0):.4f}",
                    f"{yolo_val.get('f1-score',0):.4f}",
                    "",
                ])
        writer.writerow(["speed_ms_per_img", "", "", f"{b0_ms:.2f}", "", "", f"{yolo_ms:.2f}", ""])
    print(f"  → CSV: {out}")


def main():
    print("\n" + "=" * 60)
    print("  SO SÁNH EfficientNet-B0 vs YOLOv8-Classification")
    print("=" * 60)
    print(f"Device : {DEVICE}")
    print(f"Test   : {TEST_DIR}\n")

    print("[1/2] Chạy EfficientNet-B0...")
    b0_true, b0_pred, b0_ms, class_names = run_efficientnet(None)
    b0_report = compute_metrics(b0_true, b0_pred, class_names)
    print(f"      Accuracy: {b0_report['accuracy']:.4f}  |  {b0_ms:.2f} ms/img")

    print("\n[2/2] Chạy YOLOv8-cls...")
    yolo_true, yolo_pred, yolo_ms = run_yolo(class_names)
    yolo_report = compute_metrics(yolo_true, yolo_pred, class_names)
    print(f"      Accuracy: {yolo_report['accuracy']:.4f}  |  {yolo_ms:.2f} ms/img")

    print_comparison(b0_report, yolo_report, b0_ms, yolo_ms, class_names)
    plot_comparison(b0_report, yolo_report, b0_ms, yolo_ms, class_names)
    plot_confusion_matrices(b0_true, b0_pred, yolo_true, yolo_pred, class_names)
    save_csv(b0_report, yolo_report, b0_ms, yolo_ms, class_names)

    print("\n✓ Xong. Kết quả đã lưu tại cv/results/")


if __name__ == "__main__":
    main()
