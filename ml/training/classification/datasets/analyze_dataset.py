from pathlib import Path
from collections import defaultdict
import random
import yaml
import matplotlib.pyplot as plt
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "configs" / "train_config.yaml"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".PNG"}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def count_per_class(split_dir: Path) -> dict[str, int]:
    return {
        d.name: sum(1 for f in d.iterdir() if f.suffix in IMAGE_EXTS)
        for d in sorted(split_dir.iterdir())
        if d.is_dir()
    }


def main():
    print(f"Analyzing dataset at: {PROJECT_ROOT}")
    cfg = load_config()
    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]
    print(f"Dataset root: {dataset_root}")
    stats_dir = PROJECT_ROOT / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)

    splits = ["train", "val", "test"]
    counts = {s: count_per_class(dataset_root / s) for s in splits}
    classes = sorted(counts["train"].keys())

    print(f"\n{'='*70}")
    print(f"{'Class':<45} {'Train':>6} {'Val':>5} {'Test':>5} {'Total':>6}")
    print("-" * 70)

    class_totals: dict[str, int] = {}
    grand = defaultdict(int)
    for cls in classes:
        t = counts["train"].get(cls, 0)
        v = counts["val"].get(cls, 0)
        te = counts["test"].get(cls, 0)
        total = t + v + te
        class_totals[cls] = total
        print(f"{cls:<45} {t:>6} {v:>5} {te:>5} {total:>6}")
        grand["train"] += t
        grand["val"] += v
        grand["test"] += te
        grand["total"] += total

    print("-" * 70)
    print(f"{'TOTAL':<45} {grand['train']:>6} {grand['val']:>5} {grand['test']:>5} {grand['total']:>6}")

    min_cls = min(class_totals, key=class_totals.get)
    max_cls = max(class_totals, key=class_totals.get)
    imbalance = class_totals[max_cls] / max(class_totals[min_cls], 1)

    print(f"\nMin class : {min_cls} ({class_totals[min_cls]} ảnh)")
    print(f"Max class : {max_cls} ({class_totals[max_cls]} ảnh)")
    print(f"Imbalance : {imbalance:.1f}x")
    if imbalance > 3:
        print(f"→ Nên augment: imbalance {imbalance:.1f}x > 3x. Gợi ý min_samples = {class_totals[max_cls] // 2}")
    else:
        print("→ Dataset tương đối cân bằng, augmentation không bắt buộc.")

    # Bar chart
    train_vals = [counts["train"].get(c, 0) for c in classes]
    val_vals = [counts["val"].get(c, 0) for c in classes]
    test_vals = [counts["test"].get(c, 0) for c in classes]
    x = list(range(len(classes)))
    w = 0.28

    fig, ax = plt.subplots(figsize=(max(14, len(classes) * 0.8), 6))
    ax.bar([i - w for i in x], train_vals, width=w, label="train", color="#4CAF50")
    ax.bar(x, val_vals, width=w, label="val", color="#2196F3")
    ax.bar([i + w for i in x], test_vals, width=w, label="test", color="#FF9800")
    ax.set_xticks(x)
    ax.set_xticklabels(classes, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Số ảnh")
    ax.set_title("Phân bố ảnh theo class")
    ax.legend()
    plt.tight_layout()
    out = stats_dir / "class_distribution.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"\nĐã lưu: {out}")

    # Sample images per class (5 ảnh mỗi class)
    train_dir = dataset_root / "train"
    for cls in classes:
        cls_dir = train_dir / cls
        images = [f for f in cls_dir.iterdir() if f.suffix in IMAGE_EXTS]
        samples = random.sample(images, min(5, len(images)))
        n = len(samples)
        fig, axes = plt.subplots(1, n, figsize=(3 * n, 3))
        if n == 1:
            axes = [axes]
        for ax, p in zip(axes, samples):
            ax.imshow(Image.open(p).convert("RGB"))
            ax.axis("off")
        fig.suptitle(cls, fontsize=9)
        plt.tight_layout()
        plt.savefig(stats_dir / f"samples_{cls}.png", dpi=100)
        plt.close()

    print(f"Đã lưu sample images tại: {stats_dir}/")


if __name__ == "__main__":
    main()
