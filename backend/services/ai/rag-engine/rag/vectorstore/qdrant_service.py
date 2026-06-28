"""
Qdrant abstraction layer.

Wraps qdrant-client (sync) for both ingestion and search.
Search is run via asyncio.to_thread so it doesn't block the event loop.

Collection is auto-created on first use with cosine distance.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from rag.core.exceptions import CollectionNotFoundError, VectorStoreError

logger = logging.getLogger(__name__)


class QdrantService:
    """Abstraction over Qdrant providing upsert, search, and admin operations.

    Args:
        host:            Qdrant server hostname.
        port:            HTTP port.
        collection_name: Target collection.
        vector_size:     Embedding dimensionality (must match the embedder).
        timeout:         Request timeout in seconds.
        upsert_batch_size: Vectors per upsert batch.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "plant_diseases_vn",
        vector_size: int = 768,
        timeout: float = 30.0,
        upsert_batch_size: int = 128,
    ) -> None:
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.upsert_batch_size = upsert_batch_size

        self._sync = QdrantClient(host=host, port=port, timeout=timeout)

        logger.info(
            "QdrantService init | host=%s port=%d collection=%s dim=%d",
            host, port, collection_name, vector_size,
        )

    # Collection management

    def ensure_collection(self) -> None:
        """Create the collection if it does not already exist."""
        try:
            info = self._sync.get_collection(self.collection_name)
            # qdrant-client 1.x uses points_count; older versions used vectors_count
            count = (
                getattr(info, "points_count", None)
                or getattr(info, "vectors_count", None)
                or 0
            )
            logger.info(
                "Collection '%s' exists | points=%s",
                self.collection_name, count,
            )
        except Exception:
            self._create_collection()

    def recreate_collection(self) -> None:
        """Drop (if exists) and recreate the collection."""
        try:
            self._sync.delete_collection(self.collection_name)
            logger.info("Dropped collection '%s'.", self.collection_name)
        except Exception:
            pass
        self._create_collection()

    def delete_collection(self) -> None:
        """Permanently delete the collection."""
        try:
            self._sync.delete_collection(self.collection_name)
            logger.info("Deleted collection '%s'.", self.collection_name)
        except Exception as exc:
            raise VectorStoreError(
                f"Failed to delete collection: {exc}"
            ) from exc

    def _create_collection(self) -> None:
        try:
            self._sync.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=self.vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            logger.info(
                "Created collection '%s' | dim=%d distance=COSINE",
                self.collection_name, self.vector_size,
            )
        except UnexpectedResponse as exc:
            # 409 Conflict means it was created between our check and create — that's fine
            if "already exists" in str(exc).lower() or "409" in str(exc):
                logger.info("Collection '%s' already exists.", self.collection_name)
            else:
                raise VectorStoreError(
                    f"Failed to create collection: {exc}"
                ) from exc

    # Write

    def upsert(
        self,
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        ids: Optional[list[str]] = None,
    ) -> int:
        """Upsert vectors + payloads in batches.

        Args:
            vectors:  Embedding vectors.
            payloads: Metadata dicts, one per vector.
            ids:      Optional stable string IDs. Auto-generated if omitted.

        Returns:
            Number of points upserted.
        """
        if len(vectors) != len(payloads):
            raise VectorStoreError("vectors and payloads must have equal length.")

        if ids is None:
            ids = [str(uuid.uuid4()) for _ in vectors]

        total = 0
        for batch_start in range(0, len(vectors), self.upsert_batch_size):
            batch_end = batch_start + self.upsert_batch_size
            points = [
                qmodels.PointStruct(
                    id=_str_id_to_int(ids[i]),
                    vector=vectors[i],
                    payload=payloads[i],
                )
                for i in range(batch_start, min(batch_end, len(vectors)))
            ]
            self._sync.upsert(
                collection_name=self.collection_name,
                points=points,
                wait=True,
            )
            total += len(points)
            logger.debug("Upserted batch %d–%d", batch_start, batch_start + len(points))

        logger.info("Upserted %d vectors into '%s'.", total, self.collection_name)
        return total

    # Read

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        score_threshold: float = 0.0,
        filter_payload: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Async cosine similarity search.

        Args:
            query_vector:    Embedded query.
            top_k:           Maximum results to return.
            score_threshold: Minimum similarity score (0–1).
            filter_payload:  Optional Qdrant payload filter dict.
                             Example: {"must": [{"key": "crop", "match": {"value": "lúa"}}]}

        Returns:
            List of dicts with keys: chunk_id, text, score, source, metadata.
        """
        query_filter = _build_filter(filter_payload) if filter_payload else None

        def _do_search():
            return self._sync.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                score_threshold=score_threshold,
                query_filter=query_filter,
                with_payload=True,
            )

        try:
            response = await asyncio.to_thread(_do_search)
        except Exception as exc:
            raise VectorStoreError(f"Search failed: {exc}") from exc

        results = []
        for hit in response.points:
            payload = hit.payload or {}
            results.append({
                "chunk_id": payload.get("chunk_id", str(hit.id)),
                "text": payload.get("text", ""),
                "score": hit.score,
                "source": payload.get("source", ""),
                "metadata": {k: v for k, v in payload.items()
                             if k not in ("text", "source", "chunk_id")},
            })
        return results

    def count(self) -> int:
        """Return the number of points in the collection."""
        try:
            info = self._sync.get_collection(self.collection_name)
            return (
                getattr(info, "points_count", None)
                or getattr(info, "vectors_count", None)
                or 0
            )
        except Exception:
            return 0

    def scroll_all(self, batch_size: int = 100) -> list[dict]:
        """Fetch every point in the collection and return chunk_id + text.

        Uses Qdrant's scroll API to page through all points without loading
        vectors into memory (``with_vectors=False``).

        Args:
            batch_size: Number of records fetched per scroll page.

        Returns:
            List of dicts with keys ``chunk_id``, ``text``, ``source``.
            Returns an empty list if the collection has no points.

        Raises:
            VectorStoreError: on any Qdrant communication error.
        """
        results: list[dict] = []
        offset = None  # None means start from the beginning

        while True:
            try:
                records, next_offset = self._sync.scroll(
                    collection_name=self.collection_name,
                    limit=batch_size,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as exc:
                raise VectorStoreError(f"scroll_all failed: {exc}") from exc

            for record in records:
                payload = record.payload or {}
                results.append({
                    "chunk_id": payload.get("chunk_id", str(record.id)),
                    "text":     payload.get("text", ""),
                    "source":   payload.get("source", ""),
                })

            if next_offset is None:
                break
            offset = next_offset

        logger.debug("scroll_all: fetched %d records from '%s'", len(results), self.collection_name)
        return results

    def health_check(self) -> bool:
        """Return True if Qdrant is reachable and the collection exists."""
        try:
            self._sync.get_collection(self.collection_name)
            return True
        except Exception:
            return False


# Helpers

def _str_id_to_int(id_str: str) -> int:
    """
    Qdrant requires integer or UUID point IDs.
    Convert arbitrary string IDs (chunk_id hex) to a stable integer.
    """
    try:
        return int(id_str, 16) % (2**63)   # SHA-256 hex prefix → positive int64
    except ValueError:
        return abs(hash(id_str)) % (2**63)


def _build_filter(filter_dict: dict[str, Any]) -> qmodels.Filter:
    """
    Convert a simplified filter dict into a Qdrant Filter object.

    Supported format::

        {"must": [{"key": "crop", "match": {"value": "lúa"}}]}
    """
    must_conditions = []
    for condition in filter_dict.get("must", []):
        key = condition["key"]
        match_val = condition.get("match", {}).get("value")
        if match_val is not None:
            must_conditions.append(
                qmodels.FieldCondition(
                    key=key,
                    match=qmodels.MatchValue(value=match_val),
                )
            )
    return qmodels.Filter(must=must_conditions) if must_conditions else qmodels.Filter()
