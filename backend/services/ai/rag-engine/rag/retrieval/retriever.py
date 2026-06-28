"""
Dense retrieval với tùy chọn mở rộng multi-query.

Luồng chính:
  1. Embed câu hỏi của người dùng.
  2. Tìm kiếm trên Qdrant với bộ lọc metadata tùy chọn.
  3. Nếu bật multi-query, sinh các biến thể câu hỏi, tìm từng cái,
     rồi gộp và loại trùng kết quả theo chunk_id.

Chiến lược multi-query tránh phụ thuộc vào lời gọi LLM thứ hai trong quá trình retrieval
bằng cách dùng các biến thể từ vựng đơn giản (cụm từ gợi ý theo mẫu).
"""
from __future__ import annotations

import logging
from typing import Optional

from rag.core.exceptions import RetrievalError
from rag.models.responses import RetrievedChunk
from rag.embedding.embedder import Embedder
from rag.vectorstore.qdrant_service import QdrantService

logger = logging.getLogger(__name__)


class Retriever:
    """Dense vector retriever sử dụng QdrantService.

    Args:
        embedder:          Instance của Embedder.
        qdrant:            Instance của QdrantService.
        top_k:             Số kết quả mặc định trả về.
        score_threshold:   Ngưỡng cosine similarity tối thiểu để giữ lại chunk.
        multi_query:       Bật chế độ multi-query retrieval.
        multi_query_count: Số lượng biến thể câu hỏi cần sinh.
    """

    def __init__(
        self,
        embedder: Embedder,
        qdrant: QdrantService,
        top_k: int = 5,
        score_threshold: float = 0.30,
        multi_query: bool = False,
        multi_query_count: int = 3,
    ) -> None:
        self.embedder = embedder
        self.qdrant = qdrant
        self.top_k = top_k
        self.score_threshold = score_threshold
        self.multi_query = multi_query
        self.multi_query_count = multi_query_count

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        disease_filter: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        """Thực hiện retrieval và trả về danh sách RetrievedChunk đã sắp xếp.

        Args:
            query:            Câu hỏi của người dùng.
            top_k:            Ghi đè top_k mặc định.
            score_threshold:  Ghi đè ngưỡng lọc mặc định.
            disease_filter:   Nhãn lớp để giới hạn phạm vi tìm kiếm
                              (ví dụ: "rice_Rice_Brown_Spot").

        Returns:
            Danh sách RetrievedChunk sắp xếp theo điểm giảm dần.
        """
        k = top_k or self.top_k
        threshold = score_threshold if score_threshold is not None else self.score_threshold
        payload_filter = _build_disease_filter(disease_filter)

        try:
            if self.multi_query:
                return await self._multi_query_retrieve(
                    query, k, threshold, payload_filter
                )
            return await self._single_retrieve(query, k, threshold, payload_filter)

        except Exception as exc:
            raise RetrievalError(
                f"Retrieval thất bại với query '{query[:60]}': {exc}",
                details={"query": query, "disease_filter": disease_filter},
            ) from exc

    async def _single_retrieve(
        self,
        query: str,
        top_k: int,
        threshold: float,
        payload_filter: dict | None,
    ) -> list[RetrievedChunk]:
        query_vec = self.embedder.embed_query(query)
        hits = await self.qdrant.search(
            query_vector=query_vec,
            top_k=top_k,
            score_threshold=threshold,
            filter_payload=payload_filter,
        )

        # Fallback: nếu tìm có filter không ra kết quả → thử lại không filter
        if not hits and payload_filter:
            logger.debug("Không có kết quả khi lọc; thử lại không có disease filter.")
            hits = await self.qdrant.search(
                query_vector=query_vec,
                top_k=top_k,
                score_threshold=threshold,
                filter_payload=None,
            )

        logger.debug("Đã lấy %d chunks (query='%s')", len(hits), query[:60])
        return _hits_to_chunks(hits)

    async def _multi_query_retrieve(
        self,
        query: str,
        top_k: int,
        threshold: float,
        payload_filter: dict | None,
    ) -> list[RetrievedChunk]:
        """Sinh các biến thể câu hỏi theo từ vựng, tìm từng cái, gộp kết quả."""
        variants = [query] + _generate_variants(query, self.multi_query_count - 1)
        logger.debug("Biến thể multi-query: %s", variants)

        seen: dict[str, RetrievedChunk] = {}
        for variant in variants:
            vec = self.embedder.embed_query(variant)
            hits = await self.qdrant.search(
                query_vector=vec,
                top_k=top_k,
                score_threshold=threshold,
                filter_payload=payload_filter,
            )
            for chunk in _hits_to_chunks(hits):
                # Giữ lại điểm cao nhất cho mỗi chunk_id
                existing = seen.get(chunk.chunk_id)
                if existing is None or chunk.score > existing.score:
                    seen[chunk.chunk_id] = chunk

        merged = sorted(seen.values(), key=lambda c: c.score, reverse=True)[:top_k]
        logger.debug("Multi-query gộp được %d chunk duy nhất", len(merged))
        return merged


# Helpers

def _hits_to_chunks(hits: list[dict]) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            chunk_id=h["chunk_id"],
            text=h["text"],
            score=round(h["score"], 4),
            source=h["source"],
            metadata=h.get("metadata", {}),
        )
        for h in hits
    ]


def _build_disease_filter(disease_filter: Optional[str]) -> dict | None:
    """Xây dựng bộ lọc payload Qdrant theo crop key (cafe/lua/mia/ngo)."""
    if not disease_filter:
        return None
    return {
        "must": [{"key": "crop", "match": {"value": disease_filter}}]
    }


def _generate_variants(query: str, n: int) -> list[str]:
    """
    Sinh các biến thể câu hỏi theo từ vựng cho multi-query retrieval.

    Không cần gọi LLM — cải thiện recall bằng cách diễn đạt lại câu hỏi
    theo các mẫu phổ biến trong tiếng Việt.
    """
    templates = [
        f"Triệu chứng và cách phòng trị {query}",
        f"Nguyên nhân gây ra {query}",
        f"Cách nhận biết {query}",
        f"Điều kiện phát sinh {query}",
        f"Thuốc điều trị {query}",
    ]
    return templates[:n]
