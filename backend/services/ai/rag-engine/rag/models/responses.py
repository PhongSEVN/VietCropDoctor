"""
Pydantic v2 response models for all API endpoints.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# Shared
class RetrievedChunk(BaseModel):
    """A single retrieved + optionally reranked chunk."""

    chunk_id: str
    text: str
    score: float
    source: str
    metadata: dict[str, Any] = {}


# RAG

class Latencies(BaseModel):
    embed_ms: float
    retrieve_ms: float
    rerank_ms: float
    llm_ms: float
    total_ms: float


class QueryResponse(BaseModel):
    """Response body for POST /query."""

    answer: str
    chunks: list[RetrievedChunk]
    latencies: Latencies
    model: str
    session_id: Optional[str] = None


# Ingestion

class IngestResponse(BaseModel):
    """Response body for POST /ingest and POST /reindex."""

    chunks_created: int
    documents_processed: int
    collection: str
    elapsed_seconds: float


# Collection

class CollectionStatsResponse(BaseModel):
    collection: str
    vectors_count: int
    status: str


# CV Prediction

class PredictionItem(BaseModel):
    class_name: str
    confidence: float = Field(ge=0.0, le=1.0)


class PredictResponse(BaseModel):
    disease: str
    confidence: float = Field(ge=0.0, le=1.0)
    top3: list[PredictionItem]


# Health

class HealthResponse(BaseModel):
    status: str = "ok"
    app_version: str
    model_loaded: bool
    vectordb_connected: bool
    llm_reachable: bool
    collection: str
    vectors_count: int


# Error

class ErrorResponse(BaseModel):
    error: str
    details: dict[str, Any] = {}
