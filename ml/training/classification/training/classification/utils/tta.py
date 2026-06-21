"""Test-Time Augmentation (TTA) for image classification inference.

Averages softmax probabilities over a few light, label-preserving views of the
same image (identity + horizontal flip + small rotations). It is a cheap
accuracy boost at inference time and is model-agnostic, so the per-model
evaluation here and the ensemble voting (backend) can share the same logic.

Default behaviour everywhere is TTA OFF — the caller opts in.
"""
import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TF

# Small rotation angles (degrees) used as extra TTA views, on top of the
# identity view and the horizontal flip. Kept small so the label is preserved.
TTA_ROTATIONS = (-10, 10)


def tta_views(batch: torch.Tensor):
    """Yield label-preserving augmented copies of a (B, C, H, W) batch."""
    yield batch                                   # identity
    yield torch.flip(batch, dims=[3])             # horizontal flip
    for angle in TTA_ROTATIONS:
        yield TF.rotate(batch, angle)


@torch.no_grad()
def tta_probabilities(
    model: torch.nn.Module,
    batch: torch.Tensor,
    device=None,
    enabled: bool = True,
) -> torch.Tensor:
    """Mean softmax probabilities over TTA views.

    Args:
        model: a classification model returning logits (B, num_classes).
        batch: input images (B, C, H, W).
        device: optional device to move the batch to.
        enabled: if False, do a single plain forward (no TTA).

    Returns:
        Probabilities tensor (B, num_classes) that sums to 1 per row.
    """
    if device is not None:
        batch = batch.to(device)
    model.eval()
    if not enabled:
        return F.softmax(model(batch), dim=1)

    summed = None
    n_views = 0
    for view in tta_views(batch):
        probs = F.softmax(model(view), dim=1)
        summed = probs if summed is None else summed + probs
        n_views += 1
    return summed / n_views
