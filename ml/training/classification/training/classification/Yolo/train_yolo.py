"""
Yolo/train_yolo.py
Train YOLOv8-Classification trên 25 class bệnh cây trồng.

Dataset layout (ImageFolder):
    data/dataset/train/<class_name>/*.jpg
    data/dataset/val/<class_name>/*.jpg
    data/dataset/test/<class_name>/*.jpg

Output:
    classification/results/yolo/   ← results, best.pt, last.pt
"""

import sys
import os
import shutil
from pathlib import Path

_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent.parent.parent          # training/classification/
sys.path.insert(0, str(_HERE.parent))              # utils.py

import numpy as np
import yaml
import mlflow
from sklearn.metrics import classification_report
from sklearn.metrics import f1_score
from ultralytics import YOLO

from utils import set_seed, plot_confusion_matrix

# NOTE: Class imbalance for YOLO is handled at the data level only (augmentation /
# oversampling). Ultralytics owns its training loop and does not accept a
# CrossEntropyLoss `weight=` vector, so the config-driven `imbalance.strategy`
# used by the 4 torch models does not apply here.
CONFIG_PATH = PROJECT_ROOT / "configs" / "yolo_training_config.yaml"

with open(CONFIG_PATH) as f:
    cfg = yaml.safe_load(f)

DATASET_DIR = PROJECT_ROOT / cfg["dataset"]["dir"]
IMAGE_SIZE  = cfg["dataset"]["image_size"]
NUM_CLASSES = cfg["dataset"]["num_classes"]
EPOCHS      = cfg["training"]["epochs"]
BATCH_SIZE  = cfg["training"]["batch_size"]
SEED        = cfg["training"]["seed"]
YOLO_MODEL  = cfg["model"].get("model_path", "yolov8s-cls.pt")

RESULTS_DIR = _HERE.parent / "results" / "yolo"
MODELS_DIR  = RESULTS_DIR / "models"
YOLO_RUN_DIR = _HERE / "runs"


def evaluate_macro_f1(metrics, names: dict):
    """Compute sklearn macro/weighted F1 from the confusion matrix that val() already
    produced — NO second inference pass (a re-run over the test set caused CUDA OOM on
    a 4 GB GPU).

    Ultralytics stores matrix[pred, true]; we expand the counts back into per-sample
    label lists so the metric definition matches the four torch models exactly.
    Returns (class_names, y_true, y_pred, macro_f1, weighted_f1, cm_true_pred).
    """
    nc = len(names)
    cm = np.asarray(metrics.confusion_matrix.matrix)[:nc, :nc]  # [pred, true]
    class_names = [names[i] for i in range(nc)]

    y_true: list[int] = []
    y_pred: list[int] = []
    for pred in range(nc):
        for true in range(nc):
            cnt = int(round(float(cm[pred, true])))
            if cnt:
                y_true.extend([true] * cnt)
                y_pred.extend([pred] * cnt)

    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    weighted_f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)
    # Transpose to the conventional [true, pred] orientation for plotting.
    return class_names, y_true, y_pred, macro_f1, weighted_f1, cm.T.astype(int)


def main():
    set_seed(SEED)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Ultralytics' built-in MLflow callback reads MLFLOW_EXPERIMENT_NAME; without it,
    # it auto-creates an experiment named after the runs/ folder path (junk). Pin it
    # to the shared experiment so YOLO logs land alongside the other four models.
    os.environ.setdefault("MLFLOW_TRACKING_URI", "http://localhost:5000")
    os.environ["MLFLOW_EXPERIMENT_NAME"] = "plant-disease-classification"

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment("plant-disease-classification")
    yolo_run_name = f"yolo-{YOLO_MODEL.replace('.pt', '')}"
    mlflow.start_run(run_name=yolo_run_name)
    # Canonical model_name shared with the DAG / registry / serving cv dir.
    mlflow.set_tag("model_name", "yolo")
    try:
        mlflow.log_params({
            "backbone": f"yolo-{YOLO_MODEL.replace('.pt', '')}",
            "model": YOLO_MODEL,
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "image_size": IMAGE_SIZE,
            "num_classes": NUM_CLASSES,
            "lr": cfg["optimizer"]["lr"],
            "weight_decay": cfg["optimizer"]["weight_decay"],
            "seed": SEED,
        })

        print("=" * 60)
        print("  TRAIN YOLOv8 CLASSIFICATION — 25 CLASSES")
        print("=" * 60)
        print(f"Dataset   : {DATASET_DIR}")
        print(f"Model     : {YOLO_MODEL}")
        print(f"Epochs    : {EPOCHS}  |  Batch: {BATCH_SIZE}  |  Size: {IMAGE_SIZE}")
        print(f"Results   : {RESULTS_DIR}")
        print()

        last_pt = MODELS_DIR / "last.pt"
        if last_pt.exists():
            print(f"Found last checkpoint: {last_pt}")
            print("Resuming training...\n")
            model = YOLO(str(last_pt))
            results = model.train(
                resume=True,
                project=str(YOLO_RUN_DIR),
                name="train",
                exist_ok=True,
            )
        else:
            model = YOLO(YOLO_MODEL)
            results = model.train(
                data=str(DATASET_DIR),
                task="classify",
                epochs=EPOCHS,
                imgsz=IMAGE_SIZE,
                batch=BATCH_SIZE,
                seed=SEED,
                project=str(YOLO_RUN_DIR),
                name="train",
                exist_ok=True,
                patience=cfg["output"]["early_stopping_patience"],
                lr0=cfg["optimizer"]["lr"],
                weight_decay=cfg["optimizer"]["weight_decay"],
                warmup_epochs=cfg["scheduler"]["warmup_epochs"],
                dropout=cfg["model"]["dropout"],
                workers=cfg["training"]["num_workers"],
                verbose=True,
                plots=True,
                amp=True,
            )

        yolo_weights_dir = YOLO_RUN_DIR / "train" / "weights"
        if (yolo_weights_dir / "best.pt").exists():
            shutil.copy2(yolo_weights_dir / "best.pt", MODELS_DIR / "best.pt")
            print(f"Copied best.pt → {MODELS_DIR / 'best.pt'}")
        if (yolo_weights_dir / "last.pt").exists():
            shutil.copy2(yolo_weights_dir / "last.pt", MODELS_DIR / "last.pt")
            print(f"Copied last.pt → {MODELS_DIR / 'last.pt'}")

        best_pt = MODELS_DIR / "best.pt"
        top1 = results.results_dict.get("metrics/accuracy_top1", 0.0)
        top5 = results.results_dict.get("metrics/accuracy_top5", 0.0)
        print()
        print("=" * 60)
        print(f"Training xong!")
        print(f"  Best model : {best_pt}")
        print(f"  Last model : {MODELS_DIR / 'last.pt'}")
        print(f"  Top-1 Acc  : {top1:.4f}")
        print(f"  Top-5 Acc  : {top5:.4f}")
        print("=" * 60)

        mlflow.log_metrics({"val_top1_acc": top1, "val_top5_acc": top5})

        print("\n[Đánh giá trên TEST SET...]")
        best_model = YOLO(str(best_pt))
        metrics = best_model.val(
            data=str(DATASET_DIR),
            split="test",
            imgsz=IMAGE_SIZE,
            batch=BATCH_SIZE,
            verbose=True,
        )
        test_top1 = metrics.results_dict.get("metrics/accuracy_top1", 0.0)
        test_top5 = metrics.results_dict.get("metrics/accuracy_top5", 0.0)
        print(f"\nTest Top-1 Accuracy : {test_top1:.4f}")
        print(f"Test Top-5 Accuracy : {test_top5:.4f}")

        # Macro-F1 derived from the confusion matrix val() already produced (no extra
        # inference). Same definition/ordering as the torch models -> fair comparison.
        class_names, y_true, y_pred, test_macro_f1, test_weighted_f1, cm = evaluate_macro_f1(
            metrics, best_model.names)
        print(f"Test Macro F1       : {test_macro_f1:.4f}  (unweighted mean over classes)")
        print(f"Test Weighted F1    : {test_weighted_f1:.4f}")
        print("\nClassification Report:")
        print(classification_report(y_true, y_pred, target_names=class_names, digits=4))
        plot_confusion_matrix(cm, class_names, RESULTS_DIR / "confusion_matrix.png")

        mlflow.log_metrics({
            "test_acc": test_top1,
            "test_top5_acc": test_top5,
            "test_macro_f1": test_macro_f1,
            "test_weighted_f1": test_weighted_f1,
        })
        mlflow.log_artifact(str(RESULTS_DIR / "confusion_matrix.png"))
        # YOLO's built-in MLflow integration already logs the model artifact and
        # registers it as VietCropDoctor-{yolo_run_name} — no need to do it again.
    finally:
        mlflow.end_run()


if __name__ == "__main__":
    main()
