"""
PySpark job: compute dataset statistics over the processed Parquet dataset.

Outputs to data/stats/:
  - class_distribution.json  — sample count per class
  - crop_distribution.json   — sample count per crop type
  - split_summary.json       — total / per-split counts
  - image_size_dist.json     — width/height min/max/mean (always 224x224 after preprocessing)

Usage:
    spark-submit pipelines/spark/compute_statistics.py \
        --config pipelines/spark/spark_config.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

try:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False


def run(config_path: str) -> None:
    if not SPARK_AVAILABLE:
        print("PySpark not installed.", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    sp_cfg = cfg["spark"]
    paths  = cfg["paths"]
    processed_dir = paths["processed_dir"]
    stats_dir = Path(paths["stats_output"])
    stats_dir.mkdir(parents=True, exist_ok=True)

    spark = (
        SparkSession.builder
        .master(sp_cfg["master"])
        .appName(f"{sp_cfg['app_name']}-Stats")
        .config("spark.driver.memory", sp_cfg["driver_memory"])
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(sp_cfg.get("log_level", "WARN"))

    df = spark.read.parquet(processed_dir)

    # Class distribution
    class_dist = (
        df.groupBy("class_name", "split")
        .count()
        .orderBy("class_name", "split")
        .collect()
    )
    class_dist_dict: dict[str, dict[str, int]] = {}
    for row in class_dist:
        class_dist_dict.setdefault(row["class_name"], {})[row["split"]] = row["count"]
    _write_json(stats_dir / "class_distribution.json", class_dist_dict)

    # Crop distribution
    crop_dist = (
        df.groupBy("crop_type", "split")
        .count()
        .orderBy("crop_type")
        .collect()
    )
    crop_dict: dict[str, dict[str, int]] = {}
    for row in crop_dist:
        crop_dict.setdefault(row["crop_type"], {})[row["split"]] = row["count"]
    _write_json(stats_dir / "crop_distribution.json", crop_dict)

    # Split summary
    split_summary = {
        row["split"]: row["count"]
        for row in df.groupBy("split").count().collect()
    }
    split_summary["total"] = df.count()
    _write_json(stats_dir / "split_summary.json", split_summary)

    # Image size distribution (sanity check after preprocessing)
    size_stats = df.select(
        F.min("width").alias("width_min"),
        F.max("width").alias("width_max"),
        F.avg("width").alias("width_mean"),
        F.min("height").alias("height_min"),
        F.max("height").alias("height_max"),
        F.avg("height").alias("height_mean"),
    ).first()
    _write_json(stats_dir / "image_size_dist.json", dict(size_stats.asDict()))

    print("Statistics written to:", stats_dir)
    for f in sorted(stats_dir.iterdir()):
        print(f"  {f.name}")
    spark.stop()


def _write_json(path: Path, data: object) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute dataset statistics with PySpark")
    parser.add_argument("--config", default="pipelines/spark/spark_config.yaml")
    args = parser.parse_args()
    run(args.config)
