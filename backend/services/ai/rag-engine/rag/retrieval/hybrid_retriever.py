"""
Hybrid retriever: dense vector + BM25 sparse, kết hợp bằng Reciprocal Rank Fusion.

Thiết kế
--------
* Dense retrieval xử lý tìm kiếm theo ngữ nghĩa và lọc metadata theo bệnh.
* BM25 retrieval xử lý khớp từ khoá; chạy không lọc vì chỉ mục BM25
  không lưu metadata per-chunk — reranker ở bước sau sẽ loại nhiễu.
* Công thức RRF fusion (Cormack et al., 2009):
      score(d) = α·(1/(k+r_dense)) + (1−α)·(1/(k+r_bm25))
  với k=60, α là trọng số dense (mặc định 0.7), r là thứ hạng đánh số từ 1.
  Chunk vắng mặt ở một danh sách đóng góp 0 từ phía đó.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from rag.models.responses import RetrievedChunk
from rag.retrieval.bm25_retriever import BM25Retriever
from rag.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)

# Hằng số RRF chuẩn — đủ lớn để làm giảm sự chênh lệch rank ở top.
_RRF_K = 60

# Số lượng ứng viên lấy thêm từ mỗi retriever trước khi fusion.
# Lấy 3× top_k giúp tăng recall mà không quá tốn kém.
_FETCH_MULTIPLIER = 3


class HybridRetriever:
    """Kết hợp dense (Retriever) và sparse (BM25Retriever) bằng RRF fusion.

    Args:
        dense:  Instance Dense vector retriever.
        bm25:   Instance BM25Retriever (đã được build hoặc load sẵn).
        alpha:  Trọng số cho thành phần dense (0–1).
                1.0 = thuần dense, 0.0 = thuần BM25, 0.7 = mặc định khuyến nghị.
    """

    def __init__(
        self,
        dense: Retriever,
        bm25: BM25Retriever,
        alpha: float = 0.7,
    ) -> None:
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha phải nằm trong [0, 1]; nhận được {alpha}")
        self.dense = dense
        self.bm25 = bm25
        self.alpha = alpha

        # Expose top_k để caller có thể dùng HybridRetriever như Retriever thông thường
        self.top_k = dense.top_k
        self.score_threshold = dense.score_threshold

        logger.info(
            "HybridRetriever sẵn sàng | alpha=%.2f bm25_corpus=%d",
            alpha, len(bm25),
        )

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        disease_filter: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        """Thực hiện hybrid retrieval và trả về kết quả đã fusion bằng RRF.

        Args:
            query:            Câu hỏi của người dùng.
            top_k:            Số chunk cuối cùng cần trả về.
            score_threshold:  Truyền vào dense retriever (BM25 bỏ qua tham số này).
            disease_filter:   Bộ lọc metadata chỉ áp dụng cho dense search.

        Returns:
            Danh sách RetrievedChunk sắp xếp theo điểm RRF giảm dần.
        """
        k = top_k or self.top_k
        fetch_k = min(k * _FETCH_MULTIPLIER, max(k + 10, 30))

        # Chạy dense (async) và BM25 (sync, offload sang thread) song song
        dense_task = self.dense.retrieve(
            query=query,
            top_k=fetch_k,
            score_threshold=score_threshold,
            disease_filter=disease_filter,
        )
        bm25_task = asyncio.to_thread(self.bm25.search, query, fetch_k)

        dense_results, bm25_results = await asyncio.gather(dense_task, bm25_task)

        fused = _rrf_fuse(
            dense_chunks=dense_results,
            bm25_hits=bm25_results,
            top_k=k,
            alpha=self.alpha,
            bm25=self.bm25,
        )

        logger.debug(
            "HybridRetriever | dense=%d bm25=%d fused=%d (alpha=%.2f)",
            len(dense_results), len(bm25_results), len(fused), self.alpha,
        )
        return fused


# RRF fusion

def _rrf_fuse(
    dense_chunks: list[RetrievedChunk],
    bm25_hits: list[dict],
    top_k: int,
    alpha: float,
    bm25: BM25Retriever,
    k: int = _RRF_K,
) -> list[RetrievedChunk]:
    """Gộp kết quả dense và BM25 bằng Reciprocal Rank Fusion.

    Chunk vắng mặt ở một danh sách đóng góp 0 từ phía đó (không bị phạt
    bằng rank lớn — đơn giản là không có bằng chứng từ phương thức đó).

    Args:
        dense_chunks: Kết quả dense đã sắp xếp (index 0 = rank 1).
        bm25_hits:    Danh sách dict kết quả BM25 với ``chunk_id`` và ``rank``.
        top_k:        Số kết quả cần trả về.
        alpha:        Trọng số dense.
        bm25:         BM25Retriever, dùng để tra cứu text cho chunk chỉ có ở BM25.
        k:            Hằng số RRF (mặc định 60).

    Returns:
        Danh sách top-k RetrievedChunk sắp xếp theo điểm RRF giảm dần.
    """
    # Xây bảng thứ hạng (đánh số từ 1, khớp với output của các retriever)
    dense_rank: dict[str, int] = {
        c.chunk_id: i + 1 for i, c in enumerate(dense_chunks)
    }
    bm25_rank: dict[str, int] = {
        h["chunk_id"]: h["rank"] for h in bm25_hits
    }

    # Bảng tra cứu cho dense chunks (lấy text + source + metadata)
    dense_map: dict[str, RetrievedChunk] = {c.chunk_id: c for c in dense_chunks}

    # Hợp tất cả chunk_id ứng viên từ cả hai nguồn
    all_ids = set(dense_rank) | set(bm25_rank)

    # Tính điểm RRF cho mỗi chunk
    rrf_scores: dict[str, float] = {}
    for cid in all_ids:
        dense_contribution = (
            alpha * (1.0 / (k + dense_rank[cid])) if cid in dense_rank else 0.0
        )
        bm25_contribution = (
            (1.0 - alpha) * (1.0 / (k + bm25_rank[cid])) if cid in bm25_rank else 0.0
        )
        rrf_scores[cid] = dense_contribution + bm25_contribution

    # Sắp xếp giảm dần, giữ top_k
    top_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

    result: list[RetrievedChunk] = []
    for cid in top_ids:
        score = round(rrf_scores[cid], 6)
        if cid in dense_map:
            src = dense_map[cid]
            result.append(
                RetrievedChunk(
                    chunk_id=cid,
                    text=src.text,
                    score=score,
                    source=src.source,
                    metadata=src.metadata,
                )
            )
        else:
            # Chunk chỉ có ở BM25: lấy text từ corpus BM25
            text = bm25.get_text(cid)
            if text:
                result.append(
                    RetrievedChunk(
                        chunk_id=cid,
                        text=text,
                        score=score,
                        source="",
                        metadata={},
                    )
                )

    return result
