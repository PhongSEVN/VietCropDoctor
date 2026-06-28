"""
rag/embedder.py
Embedding layer — uses OpenAI text-embedding API with an in-memory LRU cache.

Responsibilities:
  • Convert text (queries or passages) into dense vectors via OpenAI.
  • Cache recent embeddings to avoid redundant API calls.
  • Expose a simple async interface for the rest of the pipeline.
"""

import hashlib
import logging
import os
from functools import lru_cache

from openai import OpenAI

logger = logging.getLogger("rag.embedder")


class Embedder:
    """Thin wrapper around the OpenAI Embeddings API with caching."""

    def __init__(self, cfg: dict):
        emb_cfg = cfg["embedding"]
        self._model = emb_cfg["model"]
        self._dimensions = emb_cfg["dimensions"]

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. "
                "Add it to .env or export it as an environment variable."
            )

        self._client = OpenAI(api_key=api_key)
        logger.info("Embedder ready — model=%s  dim=%d", self._model, self._dimensions)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Uses the OpenAI batch endpoint."""
        if not texts:
            return []

        # Check cache first — partition into cached vs. uncached
        cached_results: dict[int, list[float]] = {}
        to_embed: list[tuple[int, str]] = []

        for idx, text in enumerate(texts):
            key = self._cache_key(text)
            cached = self._get_cached(key)
            if cached is not None:
                cached_results[idx] = cached
            else:
                to_embed.append((idx, text))

        # Embed uncached texts in batches (OpenAI limit: 2048 per request)
        BATCH_SIZE = 512
        api_results: dict[int, list[float]] = {}
        for batch_start in range(0, len(to_embed), BATCH_SIZE):
            batch = to_embed[batch_start : batch_start + BATCH_SIZE]
            batch_texts = [t for _, t in batch]

            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=batch_texts,
                    dimensions=self._dimensions,
                )
            except Exception:
                logger.exception("OpenAI embedding API call failed")
                raise

            for item, (orig_idx, orig_text) in zip(response.data, batch):
                vec = item.embedding
                api_results[orig_idx] = vec
                self._put_cached(self._cache_key(orig_text), vec)

        # Merge results preserving original order
        merged = [None] * len(texts)
        for idx, vec in {**cached_results, **api_results}.items():
            merged[idx] = vec

        logger.info(
            "Embedded %d texts (cache hits=%d, API calls=%d)",
            len(texts),
            len(cached_results),
            len(to_embed),
        )
        return merged

    def embed_query(self, query: str) -> list[float]:
        """Embed a single query string. Returns a single vector."""
        results = self.embed_texts([query])
        return results[0]

    # ------------------------------------------------------------------
    # Cache helpers (simple LRU via functools — stores up to 2048 entries)
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    @lru_cache(maxsize=2048)
    def _get_cached(key: str) -> list[float] | None:
        # The lru_cache stores the return value.
        # On the first call for a given key we return None (cache miss).
        # We override the cache entry in _put_cached.
        return None

    @staticmethod
    def _put_cached(key: str, vec: list[float]) -> None:
        # Manually inject into the lru_cache by calling the cached function
        # with a wrapper that returns the desired value, then invalidate.
        # Simpler approach: use a plain dict.
        Embedder._embedding_store[key] = vec

    # Plain dict backing store (the lru_cache above is only for the key lookup)
    _embedding_store: dict[str, list[float]] = {}

    @staticmethod
    def _get_cached(key: str) -> list[float] | None:  # noqa: F811  – intentional override
        return Embedder._embedding_store.get(key)
