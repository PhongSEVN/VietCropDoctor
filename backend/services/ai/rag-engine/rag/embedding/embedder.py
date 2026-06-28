"""
Sentence-Transformers embedding wrapper.

Model: intfloat/multilingual-e5-base
  • 768-dim vectors, cosine similarity
  • Requires "query: " prefix for queries, "passage: " for documents
  • ~1.1 GB VRAM — leaves headroom alongside the Ollama LLM (qwen2.5:7b)

Features:
  - Auto device selection (CUDA > MPS > CPU)
  - Batched encoding with tqdm progress
  - LRU cache to avoid re-embedding identical texts
  - Lazy model loading (first call triggers download/load)
"""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Optional

import torch
from sentence_transformers import SentenceTransformer

from rag.core.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

# Models that require query/passage prefixes for correct behaviour.
_PREFIX_MODELS = {
    "intfloat/multilingual-e5-base",
    "intfloat/multilingual-e5-large",
    "intfloat/e5-base-v2",
    "intfloat/e5-large-v2",
}


def _resolve_device(preference: str) -> str:
    """Return a torch device string respecting the user preference."""
    if preference == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    return preference


class Embedder:
    """Thin wrapper around SentenceTransformer with batching and LRU cache.

    Args:
        model_name:    HuggingFace model identifier.
        device:        "auto" | "cuda" | "cpu" | "mps".
        batch_size:    Texts per GPU batch.
        max_length:    Tokeniser max length.
        normalize:     L2-normalise output vectors (required for cosine sim).
        cache_size:    LRU cache entries (set 0 to disable).
    """

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-base",
        device: str = "auto",
        batch_size: int = 32,
        max_length: int = 512,
        normalize: bool = True,
        cache_size: int = 4096,
    ) -> None:
        self.model_name = model_name
        self.device = _resolve_device(device)
        self.batch_size = batch_size
        self.max_length = max_length
        self.normalize = normalize
        self._use_prefix = model_name in _PREFIX_MODELS

        self._model: Optional[SentenceTransformer] = None
        self._lock = threading.Lock()

        # Build per-instance LRU cache with configurable size
        if cache_size > 0:
            self._cache: dict[str, list[float]] = {}
            self._cache_size = cache_size
        else:
            self._cache = {}
            self._cache_size = 0

        logger.info(
            "Embedder configured | model=%s device=%s batch=%d prefix=%s",
            model_name, self.device, batch_size, self._use_prefix,
        )

    # Model lifecycle

    def load(self) -> None:
        """Eagerly load the model. Thread-safe; call at startup for warmup."""
        self._ensure_loaded()

    def _ensure_loaded(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                logger.info("Loading embedding model: %s -> %s", self.model_name, self.device)
                try:
                    self._model = SentenceTransformer(
                        self.model_name,
                        device=self.device,
                    )
                    self._model.max_seq_length = self.max_length
                    logger.info(
                        "Embedding model loaded | dim=%d",
                        self._model.get_sentence_embedding_dimension(),
                    )
                except Exception as exc:
                    raise EmbeddingError(
                        f"Failed to load model {self.model_name}: {exc}"
                    ) from exc
        return self._model

    def unload(self) -> None:
        """Free GPU memory by deleting the model."""
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("Embedding model unloaded.")

    @property
    def vector_size(self) -> int:
        model = self._ensure_loaded()
        return model.get_sentence_embedding_dimension()

    # Embedding API

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of document passages (applies "passage: " prefix)."""
        if not texts:
            return []
        prefixed = self._apply_prefix(texts, is_query=False)
        return self._encode(prefixed)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string (applies "query: " prefix)."""
        if not text.strip():
            raise EmbeddingError("Cannot embed an empty query.")
        prefixed = self._apply_prefix([text], is_query=True)
        return self._encode(prefixed)[0]

    # Private

    def _apply_prefix(self, texts: list[str], is_query: bool) -> list[str]:
        if not self._use_prefix:
            return texts
        prefix = "query: " if is_query else "passage: "
        return [prefix + t for t in texts]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        """Run encoding with optional LRU cache and GPU batching."""
        model = self._ensure_loaded()

        # Split into cache hits and misses
        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = self._cache.get(text) if self._cache_size > 0 else None
            if cached is not None:
                results[i] = cached
            else:
                miss_indices.append(i)
                miss_texts.append(text)

        if miss_texts:
            try:
                vectors = model.encode(
                    miss_texts,
                    batch_size=self.batch_size,
                    normalize_embeddings=self.normalize,
                    show_progress_bar=len(miss_texts) > 100,
                    convert_to_numpy=True,
                )
            except Exception as exc:
                raise EmbeddingError(f"Encoding failed: {exc}") from exc

            for i, (idx, text) in enumerate(zip(miss_indices, miss_texts)):
                vec = vectors[i].tolist()
                results[idx] = vec
                # Update LRU cache (evict oldest if full)
                if self._cache_size > 0:
                    if len(self._cache) >= self._cache_size:
                        oldest_key = next(iter(self._cache))
                        del self._cache[oldest_key]
                    self._cache[text] = vec

        return results  # type: ignore[return-value]
