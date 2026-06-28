"""
Environment variables override defaults. Use __ as nested delimiter.
Example: EMBEDDING__BATCH_SIZE=64 in .env (not used here — flat style).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "VietCropDoctor RAG API"
    app_version: str = "2.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # Paths
    knowledge_dir: Path = Path("rag/knowledge")
    cv_checkpoint_path: Optional[Path] = Path("cv/models/best_model.pth")
    log_file: Optional[Path] = Path("logs/app.log")

    # Embedding 
    # intfloat/multilingual-e5-base:
    #   • 278M params → ~1.1 GB VRAM  (runs alongside qwen2.5:7b via Ollama)
    #   • 768-dim vectors, 100+ languages including Vietnamese
    #   • Requires "query: " / "passage: " prefix for best quality
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_vector_size: int = 768
    embedding_batch_size: int = 32
    embedding_max_length: int = 512
    embedding_device: str = "auto"          # auto | cpu | cuda | mps
    embedding_normalize: bool = True
    embedding_cache_size: int = 4096        # LRU cache entries for dedup

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_collection: str = "plant_diseases_vn"
    qdrant_prefer_grpc: bool = False
    qdrant_timeout: float = 30.0
    qdrant_upsert_batch_size: int = 128

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64
    chunk_min_size: int = 80

    # Retrieval
    # retrieval_top_k = số chunk trả về khi KHÔNG rerank (đưa thẳng vào LLM).
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.30
    retrieval_multi_query: bool = False
    retrieval_multi_query_count: int = 3

    # Hybrid retrieval (BM25 + dense, RRF fusion)
    hybrid_retrieval: bool = True
    hybrid_alpha: float = 0.7         # dense weight; (1−alpha) goes to BM25
    bm25_index_path: str = "data/bm25_index.pkl"

    # Reranking — hai giai đoạn TÁCH BIỆT, không dùng chung một biến:
    #   rerank_candidate_k = kích thước POOL retrieve để đưa vào cross-encoder.
    #     Pool lớn (recall cao, thứ tự chưa chuẩn) là điều kiện để rerank có ích.
    #   reranker_top_k     = số chunk GIỮ LẠI sau rerank để đưa vào LLM.
    reranker_enabled: bool = True
    reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    rerank_candidate_k: int = 30
    reranker_top_k: int = 8

    # LLM
    llm_provider: str = "ollama"            # ollama | transformers
    llm_model: str = "qwen2.5:7b"
    llm_base_url: str = "http://localhost:11434"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 1024
    llm_timeout: float = 120.0
    llm_max_retries: int = 2

    # API
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )
    max_upload_size_mb: int = 20

    # CV
    cv_image_size: int = 224

    @field_validator("knowledge_dir", mode="before")
    @classmethod
    def resolve_knowledge_dir(cls, v: str | Path) -> Path:
        return Path(v)

    @field_validator("cv_checkpoint_path", "log_file", mode="before")
    @classmethod
    def resolve_optional_path(cls, v: Optional[str | Path]) -> Optional[Path]:
        return Path(v) if v else None

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached singleton Settings instance."""
    return Settings()
