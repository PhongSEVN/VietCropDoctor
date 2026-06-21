"""
utils/imbalance.py

Bộ công cụ xử lý mất cân bằng dữ liệu (class imbalance) dùng chung cho toàn bộ
5 mô hình phân loại:

* EfficientNet-B0
* MobileNetV3
* ResNet50
* Vision Transformer (ViT)
* YOLOv8-cls

Mặc dù bộ dữ liệu sau khi làm sạch đã được cải thiện, số lượng mẫu giữa các lớp
vẫn chưa cân bằng hoàn toàn (lớp lớn nhất có thể nhiều hơn lớp nhỏ nhất khoảng 10 lần).
Để giảm ảnh hưởng của hiện tượng mất cân bằng dữ liệu trong quá trình huấn luyện,
module này cung cấp ba phương pháp bổ trợ:

1. compute_class_weights(...)
   Tính trọng số cho từng lớp để sử dụng với
   nn.CrossEntropyLoss(weight=...).

2. make_weighted_sampler(...)
   Tạo WeightedRandomSampler nhằm tăng tần suất lấy mẫu của các lớp ít dữ liệu.

3. FocalLoss(...)
   Hàm mất mát Focal Loss giúp giảm ảnh hưởng của các mẫu dễ phân loại và tập trung
   nhiều hơn vào các mẫu khó hoặc các lớp thiểu số.

Các chiến lược tính trọng số lớp (đều được chuẩn hóa sao cho giá trị trung bình
của trọng số bằng 1 nhằm giữ thang đo loss ổn định giữa các lần huấn luyện):

* "balanced"
  w_c = N / (K * n_c)

  Trọng số tỉ lệ nghịch với số lượng mẫu của từng lớp.
  Đây là chiến lược mặc định và tương đương với tùy chọn "balanced"
  trong thư viện scikit-learn.

* "inverse"
  w_c = 1 / n_c

  Trọng số nghịch đảo trực tiếp với số lượng mẫu của lớp.

* "sqrt"
  w_c = sqrt(N / (K * n_c))

  Phiên bản làm mềm của phương pháp balanced,
  giúp tránh gán trọng số quá lớn cho các lớp có rất ít mẫu.

* "effective_number"
  w_c = (1 - beta) / (1 - beta^n_c)

  Dựa trên khái niệm Effective Number of Samples
  (Cui et al., CVPR 2019 - Class-Balanced Loss Based on Effective Number of Samples),
  thường cho kết quả ổn định hơn khi dữ liệu mất cân bằng mạnh.

Lưu ý:
Thứ tự chỉ số lớp luôn tuân theo sorted(class_names), tương tự cách
torchvision.datasets.ImageFolder và PlantDiseaseDataset ánh xạ nhãn.
Do đó các trọng số được tính toán sẽ khớp trực tiếp với đầu ra của mô hình
mà không cần ánh xạ lại nhãn.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import WeightedRandomSampler

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".JPG", ".PNG", ".JPEG"}
_STRATEGIES = ("balanced", "inverse", "sqrt", "effective_number")


def counts_from_samples(samples: list, num_classes: int) -> list[int]:
    """Per-class image counts from a Dataset.samples list of (path, label_idx)."""
    counter = Counter(label for _, label in samples)
    return [counter.get(i, 0) for i in range(num_classes)]


def class_distribution(split_dir: str | Path) -> tuple[list[str], list[int]]:
    """Scan an ImageFolder-style split dir -> (sorted class names, counts aligned).

    Useful for YOLO, which does not expose a samples list. The returned counts are
    indexed the same way the model orders its classes (alphabetical).
    """
    split_dir = Path(split_dir)
    class_names = sorted(d.name for d in split_dir.iterdir() if d.is_dir())
    counts = [
        sum(1 for p in (split_dir / c).iterdir() if p.suffix in IMAGE_EXTS)
        for c in class_names
    ]
    return class_names, counts


def _weights_from_counts(
    counts: list[int], strategy: str, beta: float
) -> torch.Tensor:
    """Core math: turn per-class counts into a mean-1 normalised weight tensor."""
    if strategy not in _STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy}', expected one of {_STRATEGIES}")

    counts_t = torch.tensor(counts, dtype=torch.double)
    safe = counts_t.clamp(min=1.0)  # guard against empty classes
    n_total = counts_t.sum()
    k = len(counts)

    if strategy == "balanced":
        w = n_total / (k * safe)
    elif strategy == "inverse":
        w = 1.0 / safe
    elif strategy == "sqrt":
        w = torch.sqrt(n_total / (k * safe))
    else:  # effective_number
        if not 0.0 < beta < 1.0:
            raise ValueError(f"beta must be in (0, 1), got {beta}")
        effective = (1.0 - torch.pow(beta, safe)) / (1.0 - beta)
        w = 1.0 / effective

    # Zero-out classes that truly have no samples, then normalise to mean 1.
    w = torch.where(counts_t > 0, w, torch.zeros_like(w))
    nonzero = (counts_t > 0).sum().clamp(min=1)
    w = w * (nonzero / w.sum())
    return w.float()


def compute_class_weights(
    samples: list,
    num_classes: int,
    device=None,
    strategy: str = "balanced",
    beta: float = 0.999,
) -> torch.Tensor:
    """Per-class loss weights for an imbalanced dataset.

    Backward compatible with the original signature
    ``compute_class_weights(train_ds.samples, num_classes, device)`` -- the default
    "balanced" strategy reproduces the previous inverse-frequency weights exactly.

    Args:
        samples: list of (path, label_idx) pairs, e.g. ``train_ds.samples``.
        num_classes: total number of classes.
        device: optional torch device to move the tensor to.
        strategy: one of "balanced" | "inverse" | "sqrt" | "effective_number".
        beta: only used by "effective_number" (0.99 / 0.999 / 0.9999 are typical).

    Returns:
        Float tensor of shape [num_classes], mean ~= 1.
    """
    counts = counts_from_samples(samples, num_classes)
    weights = _weights_from_counts(counts, strategy, beta)
    return weights.to(device) if device is not None else weights


def class_weights_from_dir(
    split_dir: str | Path,
    device=None,
    strategy: str = "balanced",
    beta: float = 0.999,
) -> tuple[list[str], torch.Tensor]:
    """Like compute_class_weights but counts straight from a folder (for YOLO).

    Returns (class_names, weights) so the caller can confirm the ordering.
    """
    class_names, counts = class_distribution(split_dir)
    weights = _weights_from_counts(counts, strategy, beta)
    return class_names, (weights.to(device) if device is not None else weights)


def make_weighted_sampler(samples: list, num_classes: int) -> WeightedRandomSampler:
    """Build a WeightedRandomSampler that draws classes ~uniformly per epoch.

    Plug into the TRAIN DataLoader via ``sampler=...`` (and drop ``shuffle=True``;
    the sampler already shuffles). Each minority image is then seen proportionally
    more often. Pair with an UNWEIGHTED loss to avoid double-correcting.
    """
    counts = counts_from_samples(samples, num_classes)
    per_class_w = [0.0 if c == 0 else 1.0 / c for c in counts]
    sample_weights = [per_class_w[label] for _, label in samples]
    return WeightedRandomSampler(
        weights=torch.tensor(sample_weights, dtype=torch.double),
        num_samples=len(samples),
        replacement=True,
    )


class FocalLoss(nn.Module):
    """Multi-class focal loss (Lin et al., 2017).

    loss = alpha_c * (1 - p_t)^gamma * (-log p_t)

    `gamma` focuses training on hard/misclassified examples; `alpha` (optional) is a
    per-class weight tensor -- pass the output of compute_class_weights to combine
    class weighting with focal down-weighting.
    """

    def __init__(self, gamma: float = 2.0, alpha: torch.Tensor | None = None,
                 reduction: str = "mean"):
        super().__init__()
        self.gamma = gamma
        self.register_buffer("alpha", alpha if alpha is not None else None)
        self.reduction = reduction

    def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        ce = F.cross_entropy(logits, target, weight=self.alpha, reduction="none")
        pt = torch.exp(-ce)  # prob of the true class
        loss = (1.0 - pt) ** self.gamma * ce
        if self.reduction == "mean":
            return loss.mean()
        if self.reduction == "sum":
            return loss.sum()
        return loss
