"""
PySpark job: resize, normalise, and augment crop disease images at scale.

Usage:
    spark-submit pipelines/spark/preprocess_images.py \
        --config pipelines/spark/spark_config.yaml \
        --split train

Output: Parquet files in data/processed/{split}/ with columns:
    image_id, class_name, crop_type, split, pixels (binary JPEG), width, height
"""
from __future__ import annotations

import argparse
import io
import os
import random
import sys
from pathlib import Path

import yaml

# Spark bootstrap
try:
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F
    from pyspark.sql.types import BinaryType, IntegerType, StringType, StructField, StructType
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False

try:
    from PIL import Image, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


CROP_PREFIX_MAP = {
    "Cafe": "cafe",
    "Lua":  "lua",
    "Mia":  "mia",
    "Ngo":  "ngo",
}


def _infer_crop(class_name: str) -> str:
    for prefix, crop in CROP_PREFIX_MAP.items():
        if class_name.startswith(prefix):
            return crop
    return "unknown"


def _load_and_preprocess(
    image_path: str,
    target_size: tuple[int, int],
    augment: bool,
    aug_cfg: dict,
) -> bytes:
    """Load an image from disk and apply resize + optional augmentation."""
    img = Image.open(image_path).convert("RGB")
    img = img.resize(target_size, Image.LANCZOS)

    if augment:
        if aug_cfg.get("horizontal_flip") and random.random() > 0.5:
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        if aug_cfg.get("vertical_flip") and random.random() > 0.5:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        degrees = aug_cfg.get("rotation_degrees", 0)
        if degrees:
            angle = random.uniform(-degrees, degrees)
            img = img.rotate(angle, expand=False)
        brightness = aug_cfg.get("brightness_jitter", 0)
        if brightness:
            factor = 1.0 + random.uniform(-brightness, brightness)
            img = ImageEnhance.Brightness(img).enhance(factor)
        contrast = aug_cfg.get("contrast_jitter", 0)
        if contrast:
            factor = 1.0 + random.uniform(-contrast, contrast)
            img = ImageEnhance.Contrast(img).enhance(factor)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _collect_image_paths(dataset_dir: str, split: str) -> list[tuple[str, str]]:
    """Return [(image_path, class_name), ...] for a given split."""
    split_dir = Path(dataset_dir) / split
    if not split_dir.exists():
        raise FileNotFoundError(f"Split directory not found: {split_dir}")
    pairs = []
    for cls_dir in sorted(split_dir.iterdir()):
        if cls_dir.is_dir():
            for img_file in cls_dir.glob("*.jpg"):
                pairs.append((str(img_file), cls_dir.name))
            for img_file in cls_dir.glob("*.jpeg"):
                pairs.append((str(img_file), cls_dir.name))
            for img_file in cls_dir.glob("*.png"):
                pairs.append((str(img_file), cls_dir.name))
    return pairs


def run(config_path: str, split: str = "train") -> None:
    if not SPARK_AVAILABLE:
        print("PySpark not installed — run: pip install pyspark", file=sys.stderr)
        sys.exit(1)
    if not PIL_AVAILABLE:
        print("Pillow not installed — run: pip install Pillow", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    sp_cfg = cfg["spark"]
    paths  = cfg["paths"]
    pp_cfg = cfg["preprocessing"]
    target_size = tuple(pp_cfg["target_size"])
    aug_cfg = pp_cfg.get("augmentation", {})
    augment = split == "train"

    spark = (
        SparkSession.builder
        .master(sp_cfg["master"])
        .appName(sp_cfg["app_name"])
        .config("spark.driver.memory", sp_cfg["driver_memory"])
        .config("spark.executor.memory", sp_cfg["executor_memory"])
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(sp_cfg.get("log_level", "WARN"))

    image_pairs = _collect_image_paths(paths["raw_dataset"], split)
    print(f"Found {len(image_pairs)} images in split={split}")

    schema = StructType([
        StructField("image_id",   StringType(),  nullable=False),
        StructField("class_name", StringType(),  nullable=False),
        StructField("crop_type",  StringType(),  nullable=False),
        StructField("split",      StringType(),  nullable=False),
        StructField("pixels",     BinaryType(),  nullable=False),
        StructField("width",      IntegerType(), nullable=False),
        StructField("height",     IntegerType(), nullable=False),
    ])

    def process_row(pair):
        img_path, class_name = pair
        try:
            pixels = _load_and_preprocess(img_path, target_size, augment, aug_cfg)
            image_id = Path(img_path).stem
            return (image_id, class_name, _infer_crop(class_name), split, pixels, target_size[0], target_size[1])
        except Exception as e:
            print(f"Skipping {img_path}: {e}", file=sys.stderr)
            return None

    rdd = spark.sparkContext.parallelize(image_pairs, numSlices=os.cpu_count() or 4)
    processed_rdd = rdd.map(process_row).filter(lambda x: x is not None)

    df = spark.createDataFrame(processed_rdd, schema=schema)
    output_path = str(Path(paths["processed_dir"]) / split)
    df.write.mode("overwrite").parquet(output_path)
    print(f"Saved {df.count()} rows to {output_path}")
    spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preprocess crop disease images with PySpark")
    parser.add_argument("--config", default="pipelines/spark/spark_config.yaml")
    parser.add_argument("--split", choices=["train", "val", "test"], default="train")
    args = parser.parse_args()
    run(args.config, args.split)
