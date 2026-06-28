"""
Shared Pydantic schemas used across all VietCropDoctor microservices.

vision-ai  uses: PredictResult, DiseasesResponse, HealthResponse
rag-engine uses: ChatRequest/Response, QueryRequest/Response,
                 IngestDirectoryRequest, IngestResponse,
                 CollectionStatsResponse, HealthResponse, ErrorResponse
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# CV / Vision-AI

class PredictResult(BaseModel):
    disease: str
    confidence: float
    top3: list[dict]
    explanation: str = ""
    severity: str = "mild"
    severity_score: float = 0.0
    severity_advice: str = ""
    agreement_score: float = 1.0
    ensemble_used: bool = False
    model_count: int = 1
    uncertainty_score: Optional[float] = None
    image_url: Optional[str] = None
    # OOD gate: False when the image is judged not to be a crop leaf.
    is_in_distribution: bool = True
    ood_message: Optional[str] = None
    ood_score: Optional[float] = None   # P(in-distribution), 0..1


class DiseasesResponse(BaseModel):
    diseases: list[str]


# Chat

class ChatRequest(BaseModel):
    disease: str
    question: str = Field(..., min_length=1)
    session_id: str = "default"


class ChatResponse(BaseModel):
    answer: str
    sources: list[str]


# Query

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    disease_filter: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    session_id: Optional[str] = None
    stream: bool = False
    image_url: Optional[str] = None
    retrieve_only: bool = False  # skip LLM generation; return retrieved chunks only

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, v: str) -> str:
        return v.strip()


class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    source: str
    metadata: dict[str, Any] = {}


class Latencies(BaseModel):
    embed_ms: float
    retrieve_ms: float
    rerank_ms: float
    llm_ms: float
    total_ms: float


class QueryResponse(BaseModel):
    answer: str
    chunks: list[RetrievedChunk]
    latencies: Latencies
    model: str
    session_id: Optional[str] = None


# Ingestion

class IngestDirectoryRequest(BaseModel):
    directory: Optional[str] = None
    recreate_collection: bool = False


class IngestResponse(BaseModel):
    chunks_created: int
    documents_processed: int
    collection: str
    elapsed_seconds: float


# Collection

class CollectionStatsResponse(BaseModel):
    collection: str
    vectors_count: int
    status: str


# Health

class HealthResponse(BaseModel):
    status: str = "ok"
    model_loaded: bool = False
    vectordb_connected: bool = False
    llm_reachable: bool = False
    vectors_count: int = 0


# Feedback

class FeedbackRequest(BaseModel):
    """User feedback on a diagnosis result.

    `is_correct=True`  → the predicted disease is confirmed correct.
    `is_correct=False` → `corrected_disease` must hold the real class label.
    """
    session_id: Optional[str] = None
    image_url: Optional[str] = None
    predicted_disease: str = Field(..., min_length=1)
    predicted_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_correct: bool
    corrected_disease: Optional[str] = None
    comment: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("comment", mode="before")
    @classmethod
    def strip_comment(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        return v or None


class FeedbackResponse(BaseModel):
    id: str
    confirmed_label: str
    verified_image_path: Optional[str] = None
    message: str = "Cảm ơn bạn đã góp ý!"


class FeedbackItem(BaseModel):
    id: str
    session_id: Optional[str] = None
    image_url: Optional[str] = None
    predicted_disease: str
    predicted_confidence: float
    is_correct: bool
    corrected_disease: Optional[str] = None
    confirmed_label: str
    comment: Optional[str] = None
    verified_image_path: Optional[str] = None
    created_at: str


# Error

class ErrorResponse(BaseModel):
    error: str
    details: dict[str, Any] = {}
