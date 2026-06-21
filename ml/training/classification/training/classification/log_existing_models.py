"""Attach already-trained checkpoints to their existing MLflow runs.

The overnight ``train4`` run produced 4 checkpoints but the native
``mlflow.pytorch.log_model`` call failed (client 3.x vs server 2.x version
mismatch), so the model files never made it into MLflow. This one-off script
fixes that *without retraining*: it reads each ``train4_<model>.log``, extracts
the MLflow ``run_id`` that the log printed, and logs the matching
``best_model.pth`` to that run as a plain artifact (``artifact_path="model"``).

SAFETY: this only ADDS an artifact to existing runs. It never edits metrics,
never deletes a run, and never touches any other run. It is also idempotent in
practice (re-running just re-uploads the same file under the same path).

By default it runs in DRY-RUN mode and only prints what it *would* do. Pass
``--apply`` to actually upload.

Usage:
    python log_existing_models.py            # dry run, shows the plan
    python log_existing_models.py --apply     # actually log the checkpoints
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import mlflow

_HERE = Path(__file__).resolve().parent

# model -> (log file, checkpoint path). EfficientB0 saves under its own folder;
# the other three save under results/<model>/models/ (known path inconsistency).
MODELS: dict[str, tuple[Path, Path]] = {
    "efficientb0": (_HERE / "train4_efficientb0.log", _HERE / "results" / "efficientb0" / "models" / "best_model.pth"),
    "mobilenetv3": (_HERE / "train4_mobilenetv3.log", _HERE / "results" / "mobilenetv3" / "models" / "best_model.pth"),
    "resnet50":    (_HERE / "train4_resnet50.log",    _HERE / "results" / "resnet50" / "models" / "best_model.pth"),
    "transformer": (_HERE / "train4_transformer.log", _HERE / "results" / "transformer" / "models" / "best_model.pth"),
}

RUN_ID_RE = re.compile(r"runs/([0-9a-f]{32})")


def _extract_run_id(log_path: Path) -> str | None:
    """Return the last MLflow run_id printed in a train4 log, or None."""
    if not log_path.is_file():
        return None
    matches = RUN_ID_RE.findall(log_path.read_text(encoding="utf-8", errors="ignore"))
    return matches[-1] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Log existing checkpoints to their MLflow runs.")
    parser.add_argument("--apply", action="store_true", help="Actually upload (default: dry run).")
    args = parser.parse_args()

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000"))
    print(f"MLflow tracking URI: {mlflow.get_tracking_uri()}")
    print(f"Mode: {'APPLY (will upload)' if args.apply else 'DRY RUN (no changes)'}\n")

    planned = 0
    for name, (log_path, ckpt_path) in MODELS.items():
        run_id = _extract_run_id(log_path)
        if run_id is None:
            print(f"[skip] {name}: no run_id found in {log_path.name}")
            continue
        if not ckpt_path.is_file():
            print(f"[skip] {name}: checkpoint missing at {ckpt_path}")
            continue

        size_mb = ckpt_path.stat().st_size / (1024 * 1024)
        print(f"[plan] {name}: run {run_id} <- {ckpt_path.name} ({size_mb:.1f} MB) as artifact 'model/'")
        planned += 1

        if args.apply:
            # start_run with an existing run_id resumes it; we only add an artifact.
            with mlflow.start_run(run_id=run_id):
                mlflow.log_artifact(str(ckpt_path), artifact_path="model")
            print(f"       -> uploaded to run {run_id}")

    print(f"\n{planned} model(s) {'uploaded' if args.apply else 'planned'}.")
    if not args.apply and planned:
        print("Re-run with --apply to actually upload.")


if __name__ == "__main__":
    main()
