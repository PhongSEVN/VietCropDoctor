"""
Train / val / test split for the plant disease image dataset.
Default ratio: 80% train, 10% val, 10% test.

Two modes:
  - default (random per class): keeps the original behaviour.
  - --group-aware: groups near-duplicate images by perceptual hash and assigns
    each group entirely to one split, so visually-near-identical shots of the
    same leaf cannot leak across train/val/test. Follows the "split is a variable
    worth controlling" lesson and complements the md5 dedup in clean_data.py.

A class x split distribution table is written to dst_dir/split_distribution.csv.
"""
from __future__ import annotations

import argparse
import csv
import random
import shutil
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def class_images(class_dir: Path) -> list[Path]:
    return [p for p in class_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS]


# Perceptual hashing (average hash) — no extra dependency beyond Pillow

def average_hash(path: Path, hash_size: int = 8) -> int:
    """64-bit average hash of an image (grayscale, downscaled, threshold at mean)."""
    from PIL import Image

    with Image.open(path) as img:
        small = img.convert("L").resize((hash_size, hash_size), Image.BILINEAR)
        pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for px in pixels:
        bits = (bits << 1) | (1 if px >= avg else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def group_near_duplicates(images: list[Path], threshold: int) -> list[list[Path]]:
    """Union-find grouping: images within `threshold` Hamming distance share a group."""
    hashes = [average_hash(p) for p in images]
    parent = list(range(len(images)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(len(images)):
        for j in range(i + 1, len(images)):
            if hamming(hashes[i], hashes[j]) <= threshold:
                union(i, j)

    groups: dict[int, list[Path]] = {}
    for idx, img in enumerate(images):
        groups.setdefault(find(idx), []).append(img)
    return list(groups.values())


def assign_groups(groups: list[list[Path]], ratios: tuple[float, float, float]) -> dict[str, list[Path]]:
    """Greedily assign whole groups to splits to approximate the target ratios."""
    total = sum(len(g) for g in groups)
    n_train = int(total * ratios[0])
    n_val = int(total * ratios[1])
    splits: dict[str, list[Path]] = {"train": [], "val": [], "test": []}
    for group in groups:  # groups arrive pre-shuffled
        if len(splits["train"]) < n_train:
            target = "train"
        elif len(splits["val"]) < n_val:
            target = "val"
        else:
            target = "test"
        splits[target].extend(group)
    return splits


def split_dataset(
    src_dir: str | Path,
    dst_dir: str | Path,
    ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
    seed: int = 42,
    group_aware: bool = False,
    hash_threshold: int = 5,
) -> dict[str, int]:
    """Copy images from src_dir (class subfolders) into dst_dir/{train,val,test}.

    Args:
        group_aware: if True, keep near-duplicate groups (perceptual hash) within
            one split. Default False reproduces the original random per-image split.
        hash_threshold: max Hamming distance (on the 64-bit hash) to treat two
            images as near-duplicates. Only used when group_aware is True.
    """
    src = Path(src_dir)
    dst = Path(dst_dir)
    assert abs(sum(ratios) - 1.0) < 1e-6, "Ratios must sum to 1.0"
    rng = random.Random(seed)

    counts: dict[str, int] = {"train": 0, "val": 0, "test": 0}
    per_class: list[dict] = []

    for class_dir in sorted(src.iterdir()):
        if not class_dir.is_dir():
            continue
        images = class_images(class_dir)

        if group_aware:
            groups = group_near_duplicates(images, hash_threshold)
            rng.shuffle(groups)
            splits = assign_groups(groups, ratios)
        else:
            rng.shuffle(images)
            n = len(images)
            n_train = int(n * ratios[0])
            n_val = int(n * ratios[1])
            splits = {
                "train": images[:n_train],
                "val": images[n_train:n_train + n_val],
                "test": images[n_train + n_val:],
            }

        row = {"class": class_dir.name}
        for split, files in splits.items():
            out = dst / split / class_dir.name
            out.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.copy(f, out / f.name)
            counts[split] += len(files)
            row[split] = len(files)
        per_class.append(row)

    _write_distribution(per_class, dst)
    return counts


def _write_distribution(per_class: list[dict], dst: Path) -> None:
    """Write a class x split distribution table (artifact for MLflow / the report)."""
    dst.mkdir(parents=True, exist_ok=True)
    out = dst / "split_distribution.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["class", "train", "val", "test"])
        writer.writeheader()
        for row in per_class:
            writer.writerow({k: row.get(k, 0) for k in ["class", "train", "val", "test"]})
    print(f"Saved split distribution: {out}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train/val/test split for the image dataset.")
    p.add_argument("--src", required=True, help="Source dir with class subfolders.")
    p.add_argument("--dst", required=True, help="Output dir for {train,val,test}.")
    p.add_argument("--ratios", type=float, nargs=3, default=(0.8, 0.1, 0.1),
                   metavar=("TRAIN", "VAL", "TEST"))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--group-aware", action="store_true",
                   help="Keep near-duplicate groups (perceptual hash) within one split.")
    p.add_argument("--hash-threshold", type=int, default=5,
                   help="Max Hamming distance to treat two images as near-duplicates.")
    return p.parse_args()


def main():
    args = parse_args()
    counts = split_dataset(
        args.src, args.dst, tuple(args.ratios), args.seed,
        group_aware=args.group_aware, hash_threshold=args.hash_threshold,
    )
    print(f"Split counts: {counts}")


if __name__ == "__main__":
    main()
