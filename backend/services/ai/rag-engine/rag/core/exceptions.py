"""
Hệ thống phân cấp exception cho RAG system.

Mỗi exception đều mang theo một thông báo lỗi dạng văn bản và một dict
chi tiết tuỳ chọn — có thể serialize thành response lỗi của API.
"""
from __future__ import annotations


class RAGBaseException(Exception):
    """Exception gốc cho tất cả lỗi liên quan đến RAG."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict = details or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r})"


# Ingestion

class IngestionError(RAGBaseException):
    """Lỗi xảy ra khi nạp tài liệu hoặc chia chunk thất bại."""


class FileValidationError(IngestionError):
    """Lỗi xảy ra khi file upload không hợp lệ hoặc không được phép."""


# Embedding

class EmbeddingError(RAGBaseException):
    """Lỗi xảy ra khi quá trình embedding văn bản thất bại."""


# Vector store

class VectorStoreError(RAGBaseException):
    """Lỗi xảy ra khi kết nối hoặc thao tác với Qdrant thất bại."""


class CollectionNotFoundError(VectorStoreError):
    """Lỗi xảy ra khi collection Qdrant đích không tồn tại."""


# Retrieval

class RetrievalError(RAGBaseException):
    """Lỗi xảy ra khi bước truy xuất tài liệu (retrieval) thất bại."""


# Reranking

class RerankerError(RAGBaseException):
    """Lỗi xảy ra khi model reranker hoạt động không thành công."""


# Generation

class LLMError(RAGBaseException):
    """Lỗi xảy ra khi LLM sinh câu trả lời thất bại (timeout, mất kết nối, ...)."""


class LLMUnavailableError(LLMError):
    """Lỗi xảy ra khi Ollama hoặc LLM backend không thể kết nối được."""


# Config

class ConfigError(RAGBaseException):
    """Lỗi xảy ra khi cấu hình hệ thống không hợp lệ."""
