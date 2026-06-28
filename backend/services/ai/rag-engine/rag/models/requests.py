"""
Pydantic v2 request models for all API endpoints.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    """Request body for POST /query."""

    question: str = Field(..., min_length=1, max_length=2000)
    disease_filter: Optional[str] = Field(
        default=None,
        description="Restrict retrieval to this disease class (e.g. 'rice_Rice_Brown_Spot').",
    )
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    session_id: Optional[str] = Field(default=None, max_length=64)
    stream: bool = Field(
        default=False,
        description="If true, return a streaming SSE response.",
    )

    @field_validator("question", mode="before")
    @classmethod
    def strip_question(cls, v: str) -> str:
        return v.strip()


class IngestDirectoryRequest(BaseModel):
    """Request body for POST /ingest (directory path on server)."""

    directory: str = Field(
        ...,
        description="Absolute or relative path to the knowledge directory on the server.",
    )
    recreate_collection: bool = Field(
        default=False,
        description="Drop and recreate the Qdrant collection before ingesting.",
    )


class ReindexRequest(BaseModel):
    """Request body for POST /reindex."""

    directory: Optional[str] = Field(
        default=None,
        description="Override the default knowledge directory.",
    )
