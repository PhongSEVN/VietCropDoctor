"""
Domain exception hierarchy shared across VietCropDoctor services.
"""
from __future__ import annotations


class VCDBaseException(Exception):
    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict = details or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.message!r})"


# RAG

class RAGBaseException(VCDBaseException):
    """Root exception for all RAG-related errors."""


class IngestionError(RAGBaseException):
    """Raised when document loading or chunking fails."""


class FileValidationError(IngestionError):
    """Raised on invalid or disallowed file upload."""


class EmbeddingError(RAGBaseException):
    """Raised when embedding computation fails."""


class VectorStoreError(RAGBaseException):
    """Raised on Qdrant connection or operation failure."""


class CollectionNotFoundError(VectorStoreError):
    """Raised when the target Qdrant collection does not exist."""


class RetrievalError(RAGBaseException):
    """Raised when the retrieval step fails."""


class RerankerError(RAGBaseException):
    """Raised when the reranker model fails."""


class LLMError(RAGBaseException):
    """Raised when LLM generation fails (timeout, connection, etc.)."""


class LLMUnavailableError(LLMError):
    """Raised when Ollama / LLM backend is not reachable."""


class ConfigError(RAGBaseException):
    """Raised on misconfiguration."""


# CV

class CVBaseException(VCDBaseException):
    """Root exception for all CV-related errors."""


class ModelLoadError(CVBaseException):
    """Raised when CV model checkpoint cannot be loaded."""


class InferenceError(CVBaseException):
    """Raised when image inference fails."""
