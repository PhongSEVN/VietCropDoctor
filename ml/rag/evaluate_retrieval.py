"""
Retrieval evaluation and debugging utility.

Runs a set of test queries against the Qdrant collection and prints
retrieved chunks with similarity scores. Useful for tuning chunk_size,
top_k, and score_threshold without starting the full API.

Usage:
    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --query "bệnh đạo ôn lá lúa"
    python scripts/evaluate_retrieval.py --query "triệu chứng rỉ sắt" --top-k 8 --threshold 0.2
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make the shared `rag` package (in the rag-engine service) importable.
import _bootstrap  # noqa: F401,E402  (path shim — must run before importing rag)

from rag.core.config import get_settings
from rag.core.logging_config import setup_logging
from rag.embedding.embedder import Embedder
from rag.retrieval.retriever import Retriever
from rag.reranking.reranker import Reranker
from rag.vectorstore.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

# Default evaluation queries (Vietnamese agricultural diseases)
DEFAULT_QUERIES = [
    "bệnh đạo ôn lá lúa triệu chứng",
    "cách phòng trị bệnh rỉ sắt cà phê",
    "nguyên nhân bệnh đốm nâu mía",
    "thuốc điều trị bệnh khảm lá mía",
    "bệnh cháy lá ngô",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument("--query", type=str, default=None, help="Single query to test")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--disease", type=str, default=None, help="Disease filter")
    parser.add_argument("--no-rerank", action="store_true")
    return parser.parse_args()


async def run_query(
    query: str,
    retriever: Retriever,
    reranker: Reranker,
    top_k: int,
    threshold: float,
    disease_filter: str | None,
    enable_rerank: bool,
) -> None:
    print(f"\n{'=' * 60}")
    print(f"QUERY: {query}")
    print(f"Filter: {disease_filter or 'none'} | top_k={top_k} | threshold={threshold}")
    print("=" * 60)

    chunks = await retriever.retrieve(
        query=query,
        top_k=top_k,
        score_threshold=threshold,
        disease_filter=disease_filter,
    )

    if enable_rerank and chunks:
        print(f"  [After retrieval: {len(chunks)} chunks]")
        chunks = reranker.rerank(query, chunks)

    if not chunks:
        print("  ⚠  No results found.")
        return

    for i, chunk in enumerate(chunks, 1):
        source = chunk.source.replace("\\", "/").split("/")[-2:]
        source_str = "/".join(source)
        print(f"\n  [{i}] score={chunk.score:.4f} | {source_str}")
        print(f"       {chunk.text[:200].replace(chr(10), ' ')}…")


async def main() -> None:
    setup_logging("INFO")
    args = parse_args()
    settings = get_settings()

    embedder = Embedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
    )
    embedder.load()

    qdrant = QdrantService(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_vector_size,
    )

    retriever = Retriever(
        embedder=embedder,
        qdrant=qdrant,
        top_k=args.top_k,
        score_threshold=args.threshold,
    )

    reranker = Reranker(
        model_name=settings.reranker_model,
        top_k=settings.reranker_top_k,
        enabled=not args.no_rerank,
    )
    if not args.no_rerank:
        reranker.load()

    queries = [args.query] if args.query else DEFAULT_QUERIES

    for q in queries:
        await run_query(
            query=q,
            retriever=retriever,
            reranker=reranker,
            top_k=args.top_k,
            threshold=args.threshold,
            disease_filter=args.disease,
            enable_rerank=not args.no_rerank,
        )

    print(f"\n{'=' * 60}")
    print(f"Evaluated {len(queries)} query(ies).")

    # Similarity inspection: compare two queries
    if len(queries) >= 2:
        import numpy as np
        print("\n── Similarity between query embeddings ──")
        vecs = [embedder.embed_query(q) for q in queries[:4]]
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                a, b = np.array(vecs[i]), np.array(vecs[j])
                sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
                print(f"  Q{i+1} ↔ Q{j+1}: {sim:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
