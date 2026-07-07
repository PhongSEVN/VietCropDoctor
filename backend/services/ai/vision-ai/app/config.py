"""
Vision-AI service configuration — CV model paths and constants.
"""
import os
from pathlib import Path

from vcd_shared.auth import require_env

# Paths are relative to the service root (services/vision-ai/)
_SERVICE_ROOT = Path(__file__).parent.parent

CKPT_PATH = _SERVICE_ROOT / "cv" / "results" / "mobilenetv3" / "models" / "best_model.pth"

FALLBACK_CLASSES: list[str] = [
    "Cafe_benh_dom_rong", "Cafe_benh_nam_ri_sat", "Cafe_benh_phan_trang",
    "Cafe_benh_phoma", "Cafe_benh_sau_ve_bua", "Cafe_khoe_manh",
    "Lua_benh_dao_on_co_bong", "Lua_benh_dao_on_la", "Lua_benh_dom_nau",
    "Lua_benh_sau_gai_hispa", "Lua_benh_vang_la_tungro", "Lua_khoe_manh",
    "Mia_benh_choi_co", "Mia_benh_dom_nau", "Mia_benh_kham_la",
    "Mia_benh_ri_sat_nau", "Mia_benh_than_den", "Mia_benh_thoi_hom",
    "Mia_benh_vang_la", "Mia_khoe_manh", "Mia_la_kho",
    "Ngo_benh_chay_la_lon", "Ngo_benh_dom_la_xam", "Ngo_benh_ri_sat",
    "Ngo_khoe_manh",
]

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/jpg", "image/webp"}

MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

# Ensemble
# Set ENSEMBLE_ENABLED=true in .env to activate multi-model weighted voting.
# All checkpoint paths are resolved relative to the service root.
ENSEMBLE_ENABLED: bool = os.getenv("ENSEMBLE_ENABLED", "false").lower() == "true"

# Voting weight = test macro-F1 of each model (fairer than accuracy on an
# imbalanced 25-class dataset). At load time cv_service overrides these with the
# macro-F1 recorded in MLflow (model_sync.fetch_macro_f1_weights) when reachable —
# including YOLO's real macro-F1, which its train script now logs. The values
# below are the FALLBACK used only when MLflow is unavailable; YOLO's fallback is
# its validation top-1 (0.9749) as a documented proxy. Weights are renormalised
# to sum to 1 at load time, so raw scores are fine.
ENSEMBLE_CONFIGS: list[dict] = [
    {
        "name":       "vit",
        "path":       str(_SERVICE_ROOT / "cv/results/vit/models/best_model.pth"),
        "weight":     0.9046,   # val macro-F1
        "input_size": 224,
        "kind":       "torch",
        "arch":       "vit",
    },
    {
        "name":       "mobilenetv3",
        "path":       str(_SERVICE_ROOT / "cv/results/mobilenetv3/models/best_model.pth"),
        "weight":     0.8975,   # val macro-F1
        "input_size": 224,
        "kind":       "torch",
        "arch":       "mobilenetv3",
    },
    {
        "name":       "resnet50",
        "path":       str(_SERVICE_ROOT / "cv/results/resnet50/models/best_model.pth"),
        "weight":     0.8775,   # val macro-F1
        "input_size": 224,
        "kind":       "torch",
        "arch":       "resnet50",
    },
    {
        "name":       "efficientnet_b0",
        "path":       str(_SERVICE_ROOT / "cv/results/efficientnet_b0/models/best_model.pth"),
        "weight":     0.8405,   # val macro-F1
        "input_size": 224,
        "kind":       "torch",
        "arch":       "efficientnet_b0",
    },
    {
        "name":       "yolo",
        "path":       str(_SERVICE_ROOT / "cv/results/yolo/models/best.pt"),
        "weight":     0.9749,   # proxy: val top-1 accuracy (no macro-F1 recorded)
        "input_size": 224,
        "kind":       "yolo",
        "arch":       None,
    },
]

# OOD gate (reject irrelevant images)
# Combines energy + agreement + MC-Dropout uncertainty to decide whether an image
# is actually a crop leaf. Parameters loaded from OOD_GATE_PATH when present
# (produced by scripts/fit_ood_gate.py); otherwise a heuristic default is used.
OOD_GATE_ENABLED: bool = os.getenv("OOD_GATE_ENABLED", "true").lower() == "true"
OOD_THRESHOLD: float = float(os.getenv("OOD_THRESHOLD", "0.5"))
OOD_GATE_PATH = _SERVICE_ROOT / "cv" / "results" / "ood_gate.json"

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
]

JWT_SECRET    = require_env("JWT_SECRET")
JWT_ALGORITHM = "HS256"
