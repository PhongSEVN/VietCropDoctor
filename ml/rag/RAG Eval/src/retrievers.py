"""Khởi tạo các cấu hình retriever để so sánh (ablation).

KHÔNG sửa code trong rag/ — chỉ import và lắp ráp lại. Các cấu hình:
  - dense        : Retriever (vector cosine)
  - bm25         : BM25Retriever (từ khoá)
  - hybrid@α     : HybridRetriever (RRF, quét alpha)
  - hybrid@0.7+rerank : hybrid alpha=0.7 rồi cross-encoder rerank

BM25 index được dựng TƯƠI từ Qdrant (scroll_all) thay vì đọc file .pkl — đảm bảo
khớp đúng corpus hiện tại và tránh lệ thuộc đường dẫn/CWD trong container.
Mọi cấu hình lấy depth=30 chunk (theo yêu cầu) rồi mới quy về tài liệu.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from paths import ensure_rag_importable

ensure_rag_importable()

from rag.core.config import get_settings  # noqa: E402
from rag.embedding.embedder import Embedder  # noqa: E402
from rag.models.responses import RetrievedChunk  # noqa: E402
from rag.reranking.reranker import Reranker  # noqa: E402
from rag.retrieval.bm25_retriever import BM25Retriever  # noqa: E402
from rag.retrieval.hybrid_retriever import HybridRetriever  # noqa: E402
from rag.retrieval.retriever import Retriever  # noqa: E402
from rag.vectorstore.qdrant_service import QdrantService  # noqa: E402

# Mỗi câu lấy 30 chunk trước khi quy về tài liệu (theo đề bài).
RETRIEVAL_DEPTH = 30


@dataclass
class Bundle:
    """Tập hợp thành phần dùng chung cho mọi cấu hình."""

    settings: object
    embedder: Embedder
    qdrant: QdrantService
    dense: Retriever
    bm25: BM25Retriever
    reranker: Reranker
    source_lookup: dict[str, str]  # chunk_id → source (cho nhánh BM25-only)


@dataclass
class RetrieverConfig:
    """Một cấu hình đánh giá. `retrieve` async, trả list[RetrievedChunk]."""

    name: str
    # retrieve(query, crop) — crop = lọc theo cây (None = không lọc)
    retrieve: Callable[[str, Optional[str]], Awaitable[list[RetrievedChunk]]]
    score_kind: str  # "cosine" | "bm25" | "rrf" | "cross-encoder"


def build_bundle(
    depth: int = RETRIEVAL_DEPTH,
    qdrant_host: Optional[str] = None,
    qdrant_port: Optional[int] = None,
    reranker_model: Optional[str] = None,
) -> Bundle:
    """Dựng embedder, Qdrant, dense, BM25 (từ Qdrant), reranker.

    Args:
        depth:        số chunk lấy mỗi câu.
        qdrant_host:  ghi đè host Qdrant của Settings (vd "localhost" khi chạy
                      trên host thay vì trong container — Settings mặc định
                      "qdrant" là DNS nội bộ Docker).
        qdrant_port:  ghi đè port Qdrant.

    Raises:
        RuntimeError: nếu Qdrant không kết nối được hoặc collection rỗng
                      (kèm thông điệp rõ ràng để khắc phục).
    """
    settings = get_settings()
    host = qdrant_host or settings.qdrant_host
    port = qdrant_port or settings.qdrant_port

    qdrant = QdrantService(
        host=host,
        port=port,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_vector_size,
        timeout=settings.qdrant_timeout,
    )
    if not qdrant.health_check():
        raise RuntimeError(
            f"Không kết nối được Qdrant tại {host}:{port} "
            f"(collection '{settings.qdrant_collection}'). "
            "Hãy chắc Qdrant đang chạy và đã ingest dữ liệu (chạy reindex). "
            "Nếu chạy trên host (không phải trong container), thêm: "
            "--qdrant-host localhost"
        )

    rows = qdrant.scroll_all()
    if not rows:
        raise RuntimeError(
            f"Collection '{settings.qdrant_collection}' rỗng — chưa có vector nào. "
            "Hãy ingest knowledge base vào Qdrant trước khi đánh giá."
        )

    embedder = Embedder(
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        max_length=settings.embedding_max_length,
        normalize=settings.embedding_normalize,
    )
    embedder.load()

    dense = Retriever(
        embedder=embedder,
        qdrant=qdrant,
        top_k=depth,
        score_threshold=0.0,  # lấy rộng cho đánh giá xếp hạng; ngưỡng tính riêng
    )

    corpus = [r["text"] for r in rows]
    chunk_ids = [r["chunk_id"] for r in rows]
    bm25 = BM25Retriever(corpus=corpus, chunk_ids=chunk_ids)
    source_lookup = {r["chunk_id"]: r.get("source", "") for r in rows}

    reranker = Reranker(
        model_name=reranker_model or settings.reranker_model,
        top_k=depth,           # rerank rồi giữ nguyên depth để còn map tài liệu
        enabled=True,
    )
    reranker.load()

    return Bundle(
        settings=settings,
        embedder=embedder,
        qdrant=qdrant,
        dense=dense,
        bm25=bm25,
        reranker=reranker,
        source_lookup=source_lookup,
    )


def _bm25_chunks(bundle: Bundle, query: str, depth: int) -> list[RetrievedChunk]:
    """Chạy BM25 rồi dựng RetrievedChunk (gắn text + source từ lookup)."""
    hits = bundle.bm25.search(query, depth)
    chunks: list[RetrievedChunk] = []
    for h in hits:
        cid = h["chunk_id"]
        chunks.append(
            RetrievedChunk(
                chunk_id=cid,
                text=bundle.bm25.get_text(cid),
                score=float(h["score"]),
                source=bundle.source_lookup.get(cid, ""),
                metadata={},
            )
        )
    return chunks


def build_configs(
    bundle: Bundle,
    alphas: list[float],
    depth: int = RETRIEVAL_DEPTH,
    names: Optional[list[str]] = None,
) -> list[RetrieverConfig]:
    """Tạo danh sách cấu hình. `alphas` để quét hybrid; `names` lọc tập con."""

    async def run_dense(query: str, crop: Optional[str] = None) -> list[RetrievedChunk]:
        return await bundle.dense.retrieve(
            query=query, top_k=depth, score_threshold=0.0, disease_filter=crop
        )

    async def run_bm25(query: str, crop: Optional[str] = None) -> list[RetrievedChunk]:
        # BM25 không có chỉ mục metadata để lọc → trả thô; run_eval hậu-lọc theo cây
        return await asyncio.to_thread(_bm25_chunks, bundle, query, depth)

    def make_hybrid(alpha: float) -> Callable[[str, Optional[str]], Awaitable[list[RetrievedChunk]]]:
        retriever = HybridRetriever(dense=bundle.dense, bm25=bundle.bm25, alpha=alpha)

        async def run(query: str, crop: Optional[str] = None) -> list[RetrievedChunk]:
            return await retriever.retrieve(
                query=query, top_k=depth, score_threshold=0.0, disease_filter=crop
            )

        return run

    def make_hybrid_rerank(alpha: float) -> Callable[[str, Optional[str]], Awaitable[list[RetrievedChunk]]]:
        retriever = HybridRetriever(dense=bundle.dense, bm25=bundle.bm25, alpha=alpha)

        async def run(query: str, crop: Optional[str] = None) -> list[RetrievedChunk]:
            candidates = await retriever.retrieve(
                query=query, top_k=depth, score_threshold=0.0, disease_filter=crop
            )
            return await asyncio.to_thread(
                bundle.reranker.rerank, query, candidates, depth
            )

        return run

    configs: list[RetrieverConfig] = [
        RetrieverConfig("dense", run_dense, "cosine"),
        RetrieverConfig("bm25", run_bm25, "bm25"),
    ]
    for a in alphas:
        configs.append(
            RetrieverConfig(f"hybrid@{a:g}", make_hybrid(a), "rrf")
        )
    # hybrid + rerank dùng alpha 0.7 (cấu hình production)
    configs.append(
        RetrieverConfig("hybrid@0.7+rerank", make_hybrid_rerank(0.7), "cross-encoder")
    )

    if names:
        wanted = set(names)
        configs = [c for c in configs if c.name in wanted]
    return configs
