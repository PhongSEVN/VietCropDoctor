"""
rag/retriever.py
Retrieval layer — handles all interactions with Qdrant.

Responsibilities:
  • Connect to Qdrant (docker or in-memory).
  • Ensure the target collection exists with the correct vector config.
  • Perform similarity search with optional metadata filtering.
  • Index (upsert) document chunks into the collection.
"""

import logging
import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger("rag.retriever")


class Retriever:
    """Manages the Qdrant vector store."""

    def __init__(self, cfg: dict, vector_dim: int):
        qcfg = cfg["qdrant"]
        self._collection = qcfg["collection"]
        self._top_k = cfg["reranker"]["top_k_retrieve"]

        if qcfg["mode"] == "memory":
            self._client = QdrantClient(":memory:")
            logger.warning(
                "Qdrant running in-memory — data will be lost on restart. "
                "Set qdrant.mode to 'docker' for persistence."
            )
        else:
            host = os.getenv("QDRANT_HOST", qcfg["host"])
            port = int(os.getenv("QDRANT_PORT", qcfg["port"]))
            self._client = QdrantClient(host=host, port=port)
            logger.info("Qdrant connected at %s:%d", host, port)

        self._vector_dim = vector_dim
        self._ensure_collection()

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection not in existing:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._vector_dim, distance=Distance.COSINE
                ),
            )
            logger.info(
                "Created collection '%s' (dim=%d)", self._collection, self._vector_dim
            )

    def recreate_collection(self) -> None:
        """Drop and recreate the collection (used during re-indexing)."""
        existing = [c.name for c in self._client.get_collections().collections]
        if self._collection in existing:
            self._client.delete_collection(self._collection)
            logger.info("Deleted existing collection '%s'", self._collection)
        self._ensure_collection()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def upsert_chunks(
        self, vectors: list[list[float]], chunks: list[dict]
    ) -> int:
        """Insert (or update) chunks with their vectors into Qdrant."""
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload=chunk,
            )
            for vec, chunk in zip(vectors, chunks)
        ]
        self._client.upsert(collection_name=self._collection, points=points)
        logger.info("Upserted %d points into '%s'", len(points), self._collection)
        return len(points)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        disease_name: str | None = None,
        top_k: int | None = None,
    ) -> list[dict]:
        """
        Search Qdrant for chunks similar to *query_vector*.

        If *disease_name* is provided, results are first filtered to that
        disease.  If no results pass the filter, a fallback unfiltered
        search is performed.

        Returns a list of dicts: {"text", "payload", "score"}.
        """
        limit = top_k or self._top_k

        search_filter = None
        if disease_name:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="class_name", match=MatchValue(value=disease_name)
                    )
                ]
            )

        results = self._client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=limit,
            query_filter=search_filter,
        ).points

        # Fallback: unfiltered search if filter produced no hits
        if not results and disease_name:
            logger.info(
                "No results for disease_name='%s', falling back to unfiltered search",
                disease_name,
            )
            results = self._client.query_points(
                collection_name=self._collection,
                query=query_vector,
                limit=limit,
            ).points

        return [
            {"text": r.payload["text"], "payload": r.payload, "score": r.score}
            for r in results
        ]
