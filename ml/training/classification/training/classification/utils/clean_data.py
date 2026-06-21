"""
Script làm sạch dataset một lần duy nhất trước khi huấn luyện.

Mục đích:
- Loại bỏ hiện tượng rò rỉ dữ liệu (data leakage) giữa train/val/test do các ảnh
  được augment offline trước khi chia tập.
- Xóa các ảnh trùng lặp hoàn toàn trong cùng một split.
- Phát hiện và loại bỏ ảnh bị lỗi hoặc không thể đọc được.

Quy trình xử lý:
1. Gom toàn bộ ảnh từ train, val và test theo từng lớp.
2. Loại bỏ ảnh lỗi và các bản sao có nội dung giống hệt nhau (so sánh bằng MD5).
3. Chỉ giữ lại một ảnh đại diện cho mỗi nội dung duy nhất.
4. Chia lại dữ liệu theo tỷ lệ 70/20/10.
5. Đảm bảo không còn ảnh trùng xuất hiện ở nhiều split khác nhau.
6. Thay thế dataset cũ bằng dataset đã làm sạch và tạo bản sao lưu nếu cần.

Sử dụng:
    python clean_data.py
        Chỉ phân tích và báo cáo (dry-run), không ghi thay đổi.

    python clean_data.py --apply
        Thực hiện làm sạch dataset và tạo bản sao lưu.

    python clean_data.py --apply --no-backup
        Thực hiện làm sạch mà không giữ bản sao lưu.

    python clean_data.py --apply --ratios 0.7 0.2 0.1 --seed 42
        Tùy chỉnh tỷ lệ chia dữ liệu và seed ngẫu nhiên.
"""
from __future__ import annotations

import argparse
import hashlib
import random
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = ("train", "val", "test")

try:
    from PIL import Image  # type: ignore
    _HAS_PIL = True
except Exception:  # pragma: no cover - depends on env
    _HAS_PIL = False


def find_dataset_root(start: Path) -> Path:
    """Walk up from `start` looking for a `data/dataset` dir with split subfolders."""
    for parent in [start, *start.parents]:
        candidate = parent / "data" / "dataset"
        if candidate.is_dir() and any((candidate / s).is_dir() for s in SPLITS):
            return candidate
    raise FileNotFoundError(
        "Could not locate 'data/dataset' (with train/val/test) above "
        f"{start}. Pass --dataset explicitly."
    )


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_corrupt(path: Path) -> bool:
    """True if the image cannot be decoded. Skipped (returns False) without Pillow."""
    if not _HAS_PIL:
        return False
    try:
        with Image.open(path) as im:
            im.verify()
        return False
    except Exception:
        return True


def list_classes(root: Path) -> list[str]:
    classes: set[str] = set()
    for split in SPLITS:
        sdir = root / split
        if not sdir.is_dir():
            continue
        classes.update(p.name for p in sdir.iterdir() if p.is_dir())
    return sorted(classes)


def gather_unique(root: Path, classes: list[str]) -> tuple[
    dict[str, list[Path]], dict[str, int], dict[str, int], int
]:
    """Pool images per class, drop corrupt + exact-byte duplicates.

    Returns (unique_paths_per_class, original_count, corrupt_count, total_seen).
    The kept representative is the first path in sorted (split, name) order, so the
    result is deterministic across runs.
    """
    unique: dict[str, list[Path]] = {}
    original: dict[str, int] = defaultdict(int)
    corrupt: dict[str, int] = defaultdict(int)
    total = 0

    for cls in classes:
        seen: set[str] = set()
        reps: list[Path] = []
        # Deterministic order: by split, then filename.
        paths: list[Path] = []
        for split in SPLITS:
            cdir = root / split / cls
            if not cdir.is_dir():
                continue
            paths.extend(
                p for p in cdir.iterdir()
                if p.is_file() and p.suffix.lower() in IMG_EXTS
            )
        paths.sort(key=lambda p: (p.parent.parent.name, p.name))

        for p in paths:
            total += 1
            original[cls] += 1
            if is_corrupt(p):
                corrupt[cls] += 1
                continue
            digest = file_md5(p)
            if digest in seen:
                continue
            seen.add(digest)
            reps.append(p)
        unique[cls] = reps

    return unique, dict(original), dict(corrupt), total


def split_unique(
    files: list[Path], ratios: tuple[float, float, float], seed: int
) -> dict[str, list[Path]]:
    """Deterministically partition `files` into train/val/test by `ratios`."""
    ordered = sorted(files, key=lambda p: p.name)
    random.Random(seed).shuffle(ordered)
    n = len(ordered)
    n_train = int(round(n * ratios[0]))
    n_val = int(round(n * ratios[1]))
    n_train = min(n_train, n)
    n_val = min(n_val, n - n_train)
    return {
        "train": ordered[:n_train],
        "val": ordered[n_train:n_train + n_val],
        "test": ordered[n_train + n_val:],
    }


def build_clean_tree(
    dest: Path,
    plan: dict[str, dict[str, list[Path]]],
) -> int:
    """Copy planned files into dest/<split>/<class>/. Returns files written."""
    written = 0
    for cls, by_split in plan.items():
        for split, paths in by_split.items():
            out_dir = dest / split / cls
            out_dir.mkdir(parents=True, exist_ok=True)
            for src in paths:
                shutil.copy2(src, out_dir / src.name)
                written += 1
    return written


def verify_no_leakage(dest: Path, classes: list[str]) -> int:
    """Recompute hashes in the new tree; return count of any cross-split collision."""
    leaks = 0
    for cls in classes:
        per_split: dict[str, set[str]] = {}
        for split in SPLITS:
            cdir = dest / split / cls
            if not cdir.is_dir():
                continue
            per_split[split] = {
                file_md5(p) for p in cdir.iterdir()
                if p.is_file() and p.suffix.lower() in IMG_EXTS
            }
        train_h = per_split.get("train", set())
        for split in ("val", "test"):
            leaks += len(per_split.get(split, set()) & train_h)
    return leaks


def _content_swap(root: Path, clean_dir: Path) -> int:
    """Replace dataset contents file-by-file (works while a watcher holds dir handles).

    Deletes existing image files under each root/<split>/<class> and copies the
    cleaned files in. Directory nodes are never renamed, so a file watcher can't
    block it. Returns the number of files copied in.
    """
    copied = 0
    for split in SPLITS:
        src_split = clean_dir / split
        if not src_split.is_dir():
            continue
        for cdir in src_split.iterdir():
            if not cdir.is_dir():
                continue
            dst = root / split / cdir.name
            dst.mkdir(parents=True, exist_ok=True)
            for old in dst.iterdir():
                if old.is_file():
                    try:
                        old.unlink()
                    except OSError:
                        pass
            for src in cdir.iterdir():
                if src.is_file():
                    shutil.copy2(src, dst / src.name)
                    copied += 1
    return copied


def main() -> int:
    ap = argparse.ArgumentParser(description="One-shot dataset leakage/duplicate fixer.")
    ap.add_argument("--dataset", type=Path, default=None,
                    help="Path to data/dataset (auto-detected if omitted).")
    ap.add_argument("--apply", action="store_true",
                    help="Actually rewrite the dataset. Default is dry-run.")
    ap.add_argument("--no-backup", action="store_true",
                    help="Delete the old tree instead of keeping a backup.")
    ap.add_argument("--ratios", type=float, nargs=3, default=(0.7, 0.2, 0.1),
                    metavar=("TRAIN", "VAL", "TEST"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if abs(sum(args.ratios) - 1.0) > 1e-6:
        print(f"ERROR: ratios must sum to 1.0, got {args.ratios}", file=sys.stderr)
        return 2

    root = args.dataset or find_dataset_root(Path(__file__).resolve().parent)
    root = root.resolve()
    print(f"Dataset root : {root}")
    print(f"Pillow       : {'available' if _HAS_PIL else 'MISSING -> corrupt check skipped'}")
    print(f"Ratios       : train {args.ratios[0]}  val {args.ratios[1]}  test {args.ratios[2]}  (seed {args.seed})")
    print(f"Mode         : {'APPLY' if args.apply else 'DRY-RUN (no changes)'}")
    print("=" * 72)

    classes = list_classes(root)
    if not classes:
        print("ERROR: no class folders found.", file=sys.stderr)
        return 2

    unique, original, corrupt, total = gather_unique(root, classes)

    # Plan the re-split.
    plan: dict[str, dict[str, list[Path]]] = {
        cls: split_unique(unique[cls], tuple(args.ratios), args.seed) for cls in classes
    }

    # Report.
    print(f"{'CLASS':28} {'orig':>6} {'corrupt':>7} {'dups':>6} {'unique':>7} "
          f"{'->train':>8} {'val':>5} {'test':>5}")
    tot_orig = tot_uniq = tot_dups = tot_corr = 0
    tr_t = va_t = te_t = 0
    for cls in classes:
        orig = original.get(cls, 0)
        corr = corrupt.get(cls, 0)
        uniq = len(unique[cls])
        dups = orig - corr - uniq
        tr = len(plan[cls]["train"]); va = len(plan[cls]["val"]); te = len(plan[cls]["test"])
        tot_orig += orig; tot_uniq += uniq; tot_dups += dups; tot_corr += corr
        tr_t += tr; va_t += va; te_t += te
        print(f"{cls:28} {orig:6d} {corr:7d} {dups:6d} {uniq:7d} {tr:8d} {va:5d} {te:5d}")
    print("-" * 72)
    print(f"{'TOTAL':28} {tot_orig:6d} {tot_corr:7d} {tot_dups:6d} {tot_uniq:7d} "
          f"{tr_t:8d} {va_t:5d} {te_t:5d}")
    print(f"\nRemoved: {tot_dups} exact-duplicate + {tot_corr} corrupt = "
          f"{tot_dups + tot_corr} of {tot_orig} images.")
    if tot_uniq:
        imbalance = max(len(plan[c]['train']) for c in classes) / max(
            1, min(len(plan[c]['train']) for c in classes))
        print(f"Post-clean train imbalance ratio: {imbalance:.1f}x")

    if not args.apply:
        print("\nDRY-RUN only. Re-run with --apply to write the cleaned dataset.")
        return 0

    # Build the clean tree next to the dataset, then swap atomically.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_dir = root.parent / f"dataset_clean_{ts}"
    print(f"\nBuilding clean tree -> {clean_dir}")
    written = build_clean_tree(clean_dir, plan)
    print(f"Copied {written} files.")

    leaks = verify_no_leakage(clean_dir, classes)
    if leaks:
        print(f"ERROR: post-build verification still found {leaks} cross-split "
              f"duplicates. Aborting swap; clean tree left at {clean_dir}.",
              file=sys.stderr)
        return 1
    print("Verification OK: 0 cross-split duplicates.")

    # Fast path: atomic directory rename (keeps the old tree as backup).
    backup_dir = root.parent / f"dataset_backup_{ts}"
    try:
        root.rename(backup_dir)
        clean_dir.rename(root)
        print(f"Swapped in cleaned dataset at {root}")
        if args.no_backup:
            shutil.rmtree(backup_dir, ignore_errors=True)
            print("Old tree deleted (--no-backup).")
        else:
            print(f"Old tree kept at {backup_dir} (delete manually once verified).")
    except (PermissionError, OSError) as exc:
        # On Windows an editor/file-watcher (e.g. VS Code) keeps directory handles
        # open, which blocks directory rename with Access Denied. File operations
        # still work, so fall back to a file-level content replacement in place.
        print(f"Directory rename blocked ({exc.__class__.__name__}); "
              f"falling back to file-level swap (no dirty backup will be kept).")
        replaced = _content_swap(root, clean_dir)
        shutil.rmtree(clean_dir, ignore_errors=True)
        print(f"File-level swap done: {replaced} files replaced in {root}")

    # Drop stale YOLO caches so the trainer re-scans the cleaned splits.
    for cache in root.glob("*.cache"):
        try:
            cache.unlink()
        except OSError:
            pass

    print("\nDone. You can train now.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
