"""
Global CV service state — loaded once at startup via lifespan.
Access via `from app.state import app_state`.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppState:
    model: Any = None
    class_names: list[str] = field(default_factory=list)
    transform: Any = None
    model_loaded: bool = False
    ensemble: Any = None  # EnsembleClassifier instance when ensemble_enabled=True
    ood_gate: Any = None  # OODGate instance (irrelevant-image filter)


app_state = AppState()
