import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import torchvision.transforms as T
import matplotlib.pyplot as plt
import cv2
from PIL import Image
from sklearn.metrics import classification_report, confusion_matrix
from collections import Counter

from cv.dataset import PlantDiseaseDataset, get_transforms
from cv.model import build_model

CONFIG_PATH = PROJECT_ROOT / "configs" / "train_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_model(ckpt_path: Path, device: torch.device):
    ckpt = torch.load(ckpt_path, map_location=device)
    model = build_model(ckpt["backbone"], ckpt["num_classes"], pretrained=False)
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()
    return model, ckpt["class_names"], ckpt["backbone"]


class GradCAM:
    def __init__(self, model: nn.Module, target_layer: nn.Module):
        self.model = model
        self._activations: torch.Tensor | None = None
        self._gradients: torch.Tensor | None = None
        target_layer.register_forward_hook(self._fwd_hook)
        target_layer.register_full_backward_hook(self._bwd_hook)

    def _fwd_hook(self, module, inp, out):
        self._activations = out.detach()

    def _bwd_hook(self, module, grad_in, grad_out):
        self._gradients = grad_out[0].detach()

    def generate(self, tensor: torch.Tensor, class_idx: int) -> np.ndarray:
        self.model.zero_grad()
        out = self.model(tensor)
        out[0, class_idx].backward()
        weights = self._gradients.mean(dim=(2, 3), keepdim=True)
        cam = torch.relu((weights * self._activations).sum(dim=1)).squeeze().cpu().numpy()
        cam = (cam - cam.min()) / (cam.max() - cam.min() + 1e-8)
        return cam


def get_target_layer(model: nn.Module, backbone: str) -> nn.Module:
    if backbone == "efficientnet_b0":
        return model.features[-1]
    elif backbone == "resnet50":
        return model.layer4[-1]
    elif backbone == "mobilenet_v3_large":
        return model.features[-1]
    raise ValueError(f"Unknown backbone: {backbone}")


def overlay_cam(img_path: Path, cam: np.ndarray, size: int, alpha: float = 0.45) -> np.ndarray:
    img = cv2.imread(str(img_path))
    img = cv2.resize(img, (size, size))
    heatmap = cv2.applyColorMap(np.uint8(255 * cv2.resize(cam, (size, size))), cv2.COLORMAP_JET)
    return cv2.addWeighted(img, 1 - alpha, heatmap, alpha, 0)


def main():
    cfg = load_config()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    image_size = cfg["dataset"]["image_size"]
    batch_size = cfg["training"]["batch_size"]
    num_workers = cfg["training"]["num_workers"]
    dataset_root = PROJECT_ROOT / cfg["dataset"]["dir"]

    results_dir = PROJECT_ROOT / cfg["output"].get("results_dir", "cv/results/efficientb0")
    models_dir = PROJECT_ROOT / cfg["output"].get("models_dir", "cv/results/efficientb0/models")
    gradcam_dir = results_dir / "gradcam"
    gradcam_dir.mkdir(parents=True, exist_ok=True)

    CKPT_PATH = models_dir / "best_model.pth"
    model, class_names, backbone = load_model(CKPT_PATH, device)

    test_ds = PlantDiseaseDataset(dataset_root / "test", get_transforms(image_size, cfg, train=False))
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    all_preds, all_labels = [], []
    with torch.no_grad():
        for imgs, labels in test_loader:
            imgs = imgs.to(device)
            preds = model(imgs).argmax(1).cpu()
            all_preds.extend(preds.tolist())
            all_labels.extend(labels.tolist())

    print("\n" + "=" * 60)
    print("Classification Report:")
    print(classification_report(all_labels, all_preds, target_names=class_names, digits=4))

    cm = confusion_matrix(all_labels, all_preds)
    n = len(class_names)
    fig, ax = plt.subplots(figsize=(max(10, n * 0.6), max(8, n * 0.5)))
    im = ax.imshow(cm, interpolation="nearest", cmap="Blues")
    plt.colorbar(im, ax=ax)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(class_names, rotation=90, fontsize=7)
    ax.set_yticklabels(class_names, fontsize=7)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix — Test Set")
    plt.tight_layout()
    plt.savefig(results_dir / "confusion_matrix.png", dpi=150)
    plt.close()
    print(f"Đã lưu: {results_dir / 'confusion_matrix.png'}")

    errors = [
        (class_names[t], class_names[p])
        for t, p in zip(all_labels, all_preds) if t != p
    ]
    print("\nTop-3 class bị nhầm lẫn nhiều nhất:")
    for (true_cls, pred_cls), count in Counter(errors).most_common(3):
        print(f"  {true_cls} → {pred_cls}: {count} lần")

    target_layer = get_target_layer(model, backbone)
    grad_cam = GradCAM(model, target_layer)

    preprocess = T.Compose([
        T.Resize((image_size, image_size)),
        T.ToTensor(),
        T.Normalize(cfg["augmentation"]["normalize"]["mean"], cfg["augmentation"]["normalize"]["std"]),
    ])

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".PNG"}
    test_dir = dataset_root / "test"
    generated = 0

    for cls in class_names:
        cls_dir = test_dir / cls
        if not cls_dir.exists():
            continue
        imgs = [f for f in cls_dir.iterdir() if f.suffix in IMAGE_EXTS][:3]
        class_idx = class_names.index(cls)
        for i, img_path in enumerate(imgs):
            tensor = preprocess(Image.open(img_path).convert("RGB")).unsqueeze(0).to(device)
            tensor.requires_grad_(True)
            cam = grad_cam.generate(tensor, class_idx)
            overlay = overlay_cam(img_path, cam, image_size)
            cv2.imwrite(str(gradcam_dir / f"{cls}_{i}.png"), overlay)
            generated += 1

    print(f"\nGrad-CAM: {generated} ảnh → {gradcam_dir}/")


if __name__ == "__main__":
    main()
