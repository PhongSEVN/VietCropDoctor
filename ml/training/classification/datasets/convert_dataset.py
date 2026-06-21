from pathlib import Path
import shutil
from collections import defaultdict
from sklearn.model_selection import train_test_split
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "train_config.yaml"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".PNG"}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def safe_class_name(name: str) -> str:
    return name.replace(" ", "_").replace("___", "_").strip("_")


def collect_classification(crop_dir: Path, prefix: str) -> dict[str, list[Path]]:
    result = {}
    for d in sorted(crop_dir.iterdir()):
        if not d.is_dir():
            continue
        images = [f for f in d.iterdir() if f.suffix in IMAGE_EXTS]
        if images:
            result[f"{prefix}_{safe_class_name(d.name)}"] = images
    return result


def collect_yolo(crop_dir: Path, prefix: str) -> dict[str, list[Path]]:
    yaml_path = crop_dir / "data.yaml"
    class_names: list[str] = []
    if yaml_path.exists():
        with open(yaml_path) as f:
            meta = yaml.safe_load(f)
        raw_names = meta.get("names", [])
        class_names = [
            f"class_{n}" if str(n).isdigit() else safe_class_name(str(n))
            for n in raw_names
        ]

    images_dir = crop_dir / "train" / "images"
    labels_dir = crop_dir / "train" / "labels"
    if not images_dir.exists() or not labels_dir.exists():
        print(f"  [SKIP] Cannot find train/images or train/labels in {crop_dir}")
        return {}

    result: dict[str, list[Path]] = defaultdict(list)
    for img in images_dir.iterdir():
        if img.suffix not in IMAGE_EXTS:
            continue
        label = labels_dir / img.with_suffix(".txt").name
        if not label.exists():
            continue
        lines = [ln.strip() for ln in label.read_text().splitlines() if ln.strip()]
        if not lines:
            continue
        ids = [int(ln.split()[0]) for ln in lines]
        primary = max(set(ids), key=ids.count)
        cname = class_names[primary] if primary < len(class_names) else f"class_{primary}"
        result[f"{prefix}_{cname}"].append(img)

    return dict(result)


def is_yolo(crop_dir: Path) -> bool:
    return (crop_dir / "train" / "images").exists() and (crop_dir / "train" / "labels").exists()


def split_and_copy(
    class_images: dict[str, list[Path]],
    dataset_root: Path,
    random_state: int,
) -> dict[str, dict]:
    stats = {}
    for cls, images in class_images.items():
        n = len(images)
        if n < 3:
            print(f"  [SKIP] {cls}: only {n} image(s)")
            continue
        train_imgs, temp = train_test_split(images, test_size=0.2, random_state=random_state, shuffle=True)
        val_imgs, test_imgs = train_test_split(temp, test_size=0.5, random_state=random_state, shuffle=True)

        for split, imgs in [("train", train_imgs), ("val", val_imgs), ("test", test_imgs)]:
            dest = dataset_root / split / cls
            dest.mkdir(parents=True, exist_ok=True)
            for img in imgs:
                shutil.copy2(img, dest / img.name)

        stats[cls] = {"total": n, "train": len(train_imgs), "val": len(val_imgs), "test": len(test_imgs)}
    return stats


def main():
    cfg = load_config()
    data_root = PROJECT_ROOT / "data"
    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]
    random_state = cfg["training"]["seed"]

    crops = [
        ("cafe", "cafe"),
        ("rice", "rice"),
        ("sugarcane", "sugarcane"),
    ]

    all_classes: dict[str, list[Path]] = {}

    for folder, prefix in crops:
        crop_dir = data_root / folder
        if not crop_dir.exists():
            print(f"[WARNING] {crop_dir} not found, skipping.")
            continue

        if is_yolo(crop_dir):
            print(f"\n{folder}: YOLO detection format")
            classes = collect_yolo(crop_dir, prefix)
        else:
            print(f"\n{folder}: classification format")
            classes = collect_classification(crop_dir, prefix)

        for cls, imgs in sorted(classes.items()):
            print(f"  {cls}: {len(imgs)} images")

        all_classes.update(classes)

    total_images = sum(len(v) for v in all_classes.values())
    print(f"\n{'='*60}")
    print(f"Total classes : {len(all_classes)}")
    print(f"Total images  : {total_images}")
    print(f"Output dir    : {dataset_root}")
    print("Splitting and copying...")

    stats = split_and_copy(all_classes, dataset_root, random_state)

    print(f"\n{'='*60}")
    print(f"{'Class':<45} {'Total':>6} {'Train':>6} {'Val':>5} {'Test':>5}")
    print("-" * 70)
    for cls, s in sorted(stats.items()):
        print(f"{cls:<45} {s['total']:>6} {s['train']:>6} {s['val']:>5} {s['test']:>5}")
    print("-" * 70)
    t = {k: sum(s[k] for s in stats.values()) for k in ("total", "train", "val", "test")}
    print(f"{'TOTAL':<45} {t['total']:>6} {t['train']:>6} {t['val']:>5} {t['test']:>5}")
    print(f"\nDataset saved to: {dataset_root.resolve()}")


if __name__ == "__main__":
    main()
