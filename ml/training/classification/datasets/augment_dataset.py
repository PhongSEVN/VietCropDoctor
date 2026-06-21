"""Offline oversampling: duplicate-with-augmentation minority classes in the
train split up to `augmentation.min_samples` images per class.

This is the *oversample* knob of the imbalance handling (separate from the
on-the-fly transforms in each model's dataset.py). It can be toggled for
ablation experiments:

    python augment_dataset.py                  # default: read config, oversample ON
    python augment_dataset.py --min-samples 0  # no-op (oversample OFF)
    python augment_dataset.py --clean          # remove previously generated aug_*.jpg
                                               #   -> back to the original distribution

Set `augmentation.oversample: false` in the config to disable by default.
"""
from pathlib import Path
import argparse
import yaml
from PIL import Image
import torchvision.transforms as T

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "train_config.yaml"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".PNG"}
AUG_PREFIX = "aug_"


def load_config(config_path: Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_transform(image_size: int) -> T.Compose:
    return T.Compose([
        T.RandomHorizontalFlip(),
        T.RandomVerticalFlip(),
        T.RandomRotation(30),
        T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
        T.RandomResizedCrop(image_size, scale=(0.75, 1.0)),
    ])


def real_images(cls_dir: Path) -> list[Path]:
    return [f for f in cls_dir.iterdir() if f.suffix in IMAGE_EXTS and not f.stem.startswith(AUG_PREFIX)]


def count_all(cls_dir: Path) -> int:
    return sum(1 for f in cls_dir.iterdir() if f.suffix in IMAGE_EXTS)


def augment_class(cls_dir: Path, target: int, transform: T.Compose) -> int:
    sources = real_images(cls_dir)
    if not sources:
        return 0
    needed = target - count_all(cls_dir)
    if needed <= 0:
        return 0
    generated = 0
    while generated < needed:
        src = sources[generated % len(sources)]
        img = Image.open(src).convert("RGB")
        aug = transform(img)
        out = cls_dir / f"{AUG_PREFIX}{generated:05d}_{src.stem}.jpg"
        aug.save(out, quality=90)
        generated += 1
    return generated


def clean_class(cls_dir: Path) -> int:
    removed = 0
    for f in cls_dir.iterdir():
        if f.suffix in IMAGE_EXTS and f.stem.startswith(AUG_PREFIX):
            f.unlink()
            removed += 1
    return removed


def iter_class_dirs(train_dir: Path):
    return (d for d in sorted(train_dir.iterdir()) if d.is_dir())


def run_clean(train_dir: Path) -> None:
    print(f"{'Class':<45} {'Removed':>8}")
    print("-" * 56)
    total = 0
    for cls_dir in iter_class_dirs(train_dir):
        removed = clean_class(cls_dir)
        total += removed
        print(f"{cls_dir.name:<45} {removed:>8}")
    print(f"\nRemoved {total} augmented image(s). Dataset back to original distribution.")


def run_augment(train_dir: Path, target: int, image_size: int) -> None:
    transform = get_transform(image_size)
    print(f"Target min samples per class: {target}")
    print(f"\n{'Class':<45} {'Before':>7} {'Added':>6} {'After':>6}")
    print("-" * 68)
    for cls_dir in iter_class_dirs(train_dir):
        before = count_all(cls_dir)
        added = augment_class(cls_dir, target, transform)
        after = count_all(cls_dir)
        marker = "—" if added == 0 else str(added)
        print(f"{cls_dir.name:<45} {before:>7} {marker:>6} {after:>6}")
    print("\nAugmentation complete.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Offline oversampling for the train split.")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                   help="Config file to read dataset.dir / augmentation settings from.")
    p.add_argument("--min-samples", type=int, default=None,
                   help="Override augmentation.min_samples (0 disables oversampling).")
    p.add_argument("--clean", action="store_true",
                   help="Remove previously generated aug_*.jpg and exit (original distribution).")
    return p.parse_args()


def main():
    args = parse_args()
    cfg = load_config(args.config)
    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]
    train_dir = dataset_root / "train"

    if args.clean:
        run_clean(train_dir)
        return

    aug_cfg = cfg.get("augmentation", {})
    oversample = aug_cfg.get("oversample", True)
    target = args.min_samples if args.min_samples is not None else aug_cfg.get("min_samples", 0)

    if not oversample or target <= 0:
        print("Oversample disabled (oversample=false or min_samples<=0). Nothing to do.")
        print("Tip: run with --clean to also remove old aug_*.jpg files.")
        return

    run_augment(train_dir, target, cfg["dataset"]["image_size"])


if __name__ == "__main__":
    main()
