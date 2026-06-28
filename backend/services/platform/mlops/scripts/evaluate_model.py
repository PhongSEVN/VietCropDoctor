"""
Evaluate the Production MLflow model against a held-out test set.

Usage:
    python evaluate_model.py \
        --model-name VietCropDoctor-Classifier \
        --test-dir   data/training/test \
        --output     evaluation_result.json

Exits 0 on completion (even if quality is below threshold).
The caller (GitHub Actions workflow) is responsible for checking the JSON.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _load_model(model_name: str):
    import mlflow
    import mlflow.pytorch

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
    mlflow.set_tracking_uri(tracking_uri)
    client = mlflow.tracking.MlflowClient()

    versions = client.get_latest_versions(model_name, stages=["Production"])
    if not versions:
        raise RuntimeError(
            f"No model in 'Production' stage for registered model '{model_name}'. "
            "Run training and promote a model first."
        )

    ver = versions[0]
    model_uri = f"models:/{model_name}/Production"
    logger.info("Loading model %s  version=%s  run_id=%s", model_uri, ver.version, ver.run_id)

    model = mlflow.pytorch.load_model(model_uri, map_location="cpu")
    model.eval()
    return model, ver


def _build_transform():
    import torchvision.transforms as T

    return T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def _evaluate(model, test_dir: Path, transform) -> dict:
    import torch
    from PIL import Image
    from sklearn.metrics import classification_report, f1_score

    class_names = sorted(d.name for d in test_dir.iterdir() if d.is_dir())
    if not class_names:
        raise RuntimeError(f"No class subdirectories found in {test_dir}")

    class_to_idx = {c: i for i, c in enumerate(class_names)}
    logger.info("Found %d classes in %s", len(class_names), test_dir)

    y_true: list[int] = []
    y_pred: list[int] = []
    skipped = 0

    for cls in class_names:
        cls_dir = test_dir / cls
        images = list(cls_dir.glob("*.jpg")) + list(cls_dir.glob("*.jpeg")) + list(cls_dir.glob("*.png"))
        for img_path in images:
            try:
                img = Image.open(img_path).convert("RGB")
                tensor = transform(img).unsqueeze(0)
                with torch.no_grad():
                    logits = model(tensor)
                    pred_idx = int(logits.argmax(dim=1).item())
                y_true.append(class_to_idx[cls])
                y_pred.append(pred_idx)
            except Exception as exc:
                logger.warning("Skipping %s: %s", img_path.name, exc)
                skipped += 1

    if not y_true:
        raise RuntimeError("No test samples could be processed.")

    f1  = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))
    acc = sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)

    # Per-class breakdown (for context in the GitHub issue body)
    report = classification_report(
        y_true, y_pred,
        target_names=class_names,
        zero_division=0,
        output_dict=True,
    )
    per_class = {
        cls: {
            "precision": round(v["precision"], 4),
            "recall":    round(v["recall"],    4),
            "f1-score":  round(v["f1-score"],  4),
            "support":   v["support"],
        }
        for cls, v in report.items()
        if cls in class_names
    }

    logger.info(
        "Evaluation complete: val_f1=%.4f  accuracy=%.4f  n=%d  skipped=%d",
        f1, acc, len(y_true), skipped,
    )

    return {
        "val_f1":   round(f1,  4),
        "accuracy": round(acc, 4),
        "n_samples": len(y_true),
        "n_skipped": skipped,
        "n_classes":  len(class_names),
        "per_class":  per_class,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Production MLflow model")
    parser.add_argument("--model-name", default="VietCropDoctor-Classifier")
    parser.add_argument("--test-dir",   default="data/training/test")
    parser.add_argument("--output",     default="evaluation_result.json")
    args = parser.parse_args()

    test_dir = Path(args.test_dir)
    if not test_dir.exists():
        logger.error("Test directory not found: %s", test_dir)
        result = {"val_f1": 0.0, "error": "test_dir_not_found", "n_samples": 0}
        Path(args.output).write_text(json.dumps(result, indent=2))
        sys.exit(0)

    try:
        model, ver = _load_model(args.model_name)
    except RuntimeError as exc:
        logger.error("%s", exc)
        result = {"val_f1": 0.0, "error": str(exc), "n_samples": 0}
        Path(args.output).write_text(json.dumps(result, indent=2))
        sys.exit(0)

    transform = _build_transform()

    try:
        metrics = _evaluate(model, test_dir, transform)
    except RuntimeError as exc:
        logger.error("%s", exc)
        result = {"val_f1": 0.0, "error": str(exc), "n_samples": 0,
                  "model_version": ver.version, "run_id": ver.run_id}
        Path(args.output).write_text(json.dumps(result, indent=2))
        sys.exit(0)

    result = {
        **metrics,
        "model_version": ver.version,
        "run_id":        ver.run_id,
        "model_name":    args.model_name,
    }

    out_path = Path(args.output)
    out_path.write_text(json.dumps(result, indent=2))
    logger.info("Results written to %s", out_path)
    print(json.dumps({k: v for k, v in result.items() if k != "per_class"}, indent=2))


if __name__ == "__main__":
    main()
