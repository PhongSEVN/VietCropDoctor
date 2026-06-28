"""
Cross-encoder reranker.

Model: cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
  • Multilingual (including Vietnamese)
  • ~117M params — loads to CPU to save GPU VRAM
  • Re-scores (query, passage) pairs for precision

The reranker is optional and can be disabled via config.
When disabled, the retriever's ranked list is returned as-is.
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Optional

from rag.core.exceptions import RerankerError
from rag.models.responses import RetrievedChunk

logger = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    """Map a cross-encoder logit to (0, 1). Monotonic — ranking unchanged."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


class Reranker:
    """CrossEncoder reranker with lazy loading and optional disable.

    Args:
        model_name: HuggingFace cross-encoder model path.
        top_k:      Return this many chunks after reranking.
        enabled:    If False, pass-through without scoring.
        device:     "cpu" recommended — saves VRAM alongside embedding model.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
        top_k: int = 8,
        enabled: bool = True,
        device: str = "cpu",
        normalize: bool = True,
    ) -> None:
        self.model_name = model_name
        self.top_k = top_k
        self.enabled = enabled
        self.device = device
        self.normalize = normalize

        self._model = None
        self._lock = threading.Lock()

        if enabled:
            logger.info("Reranker configured | model=%s top_k=%d", model_name, top_k)
        else:
            logger.info("Reranker disabled.")

    def load(self) -> None:
        """Eagerly load the reranker model."""
        if self.enabled:
            self._ensure_loaded()

    def _ensure_loaded(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import CrossEncoder  # lazy import
                    logger.info("Loading reranker: %s -> %s", self.model_name, self.device)
                    self._model = CrossEncoder(
                        self.model_name,
                        device=self.device,
                        max_length=512,
                    )
                    logger.info("Reranker loaded.")
                except Exception as exc:
                    raise RerankerError(
                        f"Failed to load reranker {self.model_name}: {exc}"
                    ) from exc
        return self._model

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: Optional[int] = None,
    ) -> list[RetrievedChunk]:
        """Re-score candidates and return top_k sorted by new score.

        Args:
            query:      User question.
            candidates: Retriever output.
            top_k:      Override default top_k.

        Returns:
            Reranked + trimmed list of RetrievedChunk (scores updated).
        """
        k = top_k or self.top_k

        if not self.enabled or not candidates:
            return candidates[:k]

        model = self._ensure_loaded()
        pairs = [(query, chunk.text) for chunk in candidates]

        try:
            scores = model.predict(pairs)
        except Exception as exc:
            # Fallback: never drop context on failure — keep retrieval order.
            logger.warning("Reranker failed, falling back to retrieval order: %s", exc)
            return candidates[:k]

        if len(scores) != len(candidates):
            logger.warning(
                "Reranker score count mismatch (%d vs %d), falling back.",
                len(scores), len(candidates),
            )
            return candidates[:k]

        # Re-score; keep the retrieval index so ties resolve deterministically
        # back to the first-stage order (stable sort) instead of arbitrarily.
        rescored = []
        for idx, (chunk, raw) in enumerate(zip(candidates, scores)):
            value = _sigmoid(float(raw)) if self.normalize else float(raw)
            rescored.append((idx, raw, value, chunk))

        rescored.sort(key=lambda t: (-t[2], t[0]))

        result = [
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                score=round(value, 4),
                source=chunk.source,
                metadata=chunk.metadata,
            )
            for _, _, value, chunk in rescored[:k]
        ]
        logger.debug(
            "Reranked %d -> %d chunks | top_score=%.4f",
            len(candidates), len(result), result[0].score if result else 0.0,
        )
        return result
