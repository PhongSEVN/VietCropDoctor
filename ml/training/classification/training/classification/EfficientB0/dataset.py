from pathlib import Path
from PIL import Image
import torch
from torch.utils.data import Dataset
import torchvision.transforms as T

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".PNG"}


class PlantDiseaseDataset(Dataset):
    def __init__(self, root: Path, transform=None):
        self.classes = sorted(d.name for d in root.iterdir() if d.is_dir())
        self.class_to_idx = {c: i for i, c in enumerate(self.classes)}
        self.samples: list[tuple[Path, int]] = []
        for cls in self.classes:
            for img in (root / cls).iterdir():
                if img.suffix in IMAGE_EXTS:
                    self.samples.append((img, self.class_to_idx[cls]))
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        path, label = self.samples[idx]
        try:
            img = Image.open(path).convert("RGB")
        except Exception:
            img = Image.new("RGB", (224, 224), (0, 0, 0))
        if self.transform:
            img = self.transform(img)
        return img, label


def get_transforms(image_size: int, cfg: dict, train: bool = True) -> T.Compose:
    mean = cfg["augmentation"]["normalize"]["mean"]
    std = cfg["augmentation"]["normalize"]["std"]

    if train:
        aug = cfg["augmentation"]
        ops = [T.Resize((image_size, image_size))]
        if aug.get("random_horizontal_flip"):
            ops.append(T.RandomHorizontalFlip())
        if aug.get("random_vertical_flip"):
            ops.append(T.RandomVerticalFlip())
        if aug.get("random_rotation", 0) > 0:
            ops.append(T.RandomRotation(aug["random_rotation"]))
        cj = aug.get("color_jitter", {})
        if cj:
            ops.append(T.ColorJitter(
                brightness=cj.get("brightness", 0),
                contrast=cj.get("contrast", 0),
                saturation=cj.get("saturation", 0),
            ))
        ops += [T.ToTensor(), T.Normalize(mean, std)]
    else:
        ops = [T.Resize((image_size, image_size)), T.ToTensor(), T.Normalize(mean, std)]

    return T.Compose(ops)
