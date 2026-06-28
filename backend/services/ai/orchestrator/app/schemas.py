from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class OrchestrationRequest(BaseModel):
    """Input to the orchestrator: image bytes (base64) + optional text query."""
    image_base64: str = Field(..., description="Base64-encoded image bytes")
    query: Optional[str] = Field(
        default=None,
        description="Optional follow-up question about the detected disease",
    )
    session_id: Optional[str] = None


class VisionResult(BaseModel):
    disease: str
    confidence: float
    severity: str
    severity_score: float
    severity_advice: str
    top3: list[dict]
    uncertainty_score: Optional[float] = None
    ensemble_used: bool = False
    # Passed through from vision-ai /predict so the client keeps full fidelity
    # (OOD gate, confidence explanation, stored image URL) when the diagnosis
    # flows through the Orchestrator instead of calling /predict directly.
    explanation: str = ""
    agreement_score: float = 1.0
    model_count: int = 1
    image_url: Optional[str] = None
    is_in_distribution: bool = True
    ood_message: Optional[str] = None
    ood_score: Optional[float] = None


class RetrievalResult(BaseModel):
    answer: str
    sources: list[str]
    chunks_used: int


class Recommendation(BaseModel):
    immediate_actions: list[str]
    preventive_measures: list[str]
    treatment_options: list[str]
    monitoring_advice: str
    urgency: str   # "low" | "medium" | "high" | "critical"


class OrchestrationResponse(BaseModel):
    session_id: Optional[str]
    vision: VisionResult
    knowledge: Optional[RetrievalResult] = None
    # Optional: omitted when the pipeline stops early (e.g. out-of-distribution
    # image) before reasoning/recommendation runs.
    recommendation: Optional[Recommendation] = None
    reasoning_summary: str
    latency_ms: dict[str, float] = {}


class OrchestrationHealthResponse(BaseModel):
    status: str
    vision_ai_reachable: bool
    rag_engine_reachable: bool
    ollama_reachable: bool
