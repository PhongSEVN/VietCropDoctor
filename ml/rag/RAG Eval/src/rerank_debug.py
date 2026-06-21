"""
Tiện ích gỡ lỗi reranker — KHÔNG dùng trong production hot-path.

Mục đích: trả lời câu hỏi "rerank có làm rơi mất chunk liên quan không?"
bằng cách so sánh tập chunk liên quan TRƯỚC và SAU khi rerank.

Dùng ở mức CHUNK (ground_truth là tập chunk_id liên quan), khác với
run_eval.py vốn đánh giá ở mức TÀI LIỆU. Đây là nơi rerank thật sự lộ giá
trị (hoặc lộ lỗi), vì rerank chỉ đảo thứ tự — phải nhìn từng chunk mới thấy.
"""
from __future__ import annotations

import logging
from typing import Iterable, Protocol

logger = logging.getLogger("rerank_debug")


class _HasChunkId(Protocol):
    chunk_id: str
    text: str


def _ids(chunks: Iterable[_HasChunkId]) -> list[str]:
    return [c.chunk_id for c in chunks]


def _recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hit = sum(1 for cid in ranked_ids[:k] if cid in relevant)
    return hit / len(relevant)


def compare_retrieval_vs_rerank(
    query: str,
    retrieved: list[_HasChunkId],
    reranked: list[_HasChunkId],
    ground_truth: Iterable[str],
    k: int | None = None,
) -> dict:
    """So sánh việc giữ chunk liên quan trước/sau rerank.

    Args:
        query:        text truy vấn (để log).
        retrieved:    chunk theo thứ tự retrieval (POOL, mỗi phần tử có .chunk_id).
        reranked:     chunk theo thứ tự rerank (đã cắt còn reranker_top_k).
        ground_truth: tập chunk_id liên quan (nhãn chuẩn ở mức chunk).
        k:            mốc tính recall@k. Mặc định = số chunk reranked trả về.

    Returns:
        dict gồm:
          - recall_retrieval / recall_rerank / recall_delta (theo cùng k)
          - overlap_relevant: chunk liên quan còn giữ sau rerank
          - lost_relevant:    chunk liên quan CÓ trong pool nhưng BỊ rerank loại
          - gained_rank:      chunk liên quan được rerank đẩy vào top-k mà
                              retrieval top-k không có (rerank cứu được)
    """
    gt = set(ground_truth)
    retrieved_ids = _ids(retrieved)
    reranked_ids = _ids(reranked)
    k = k if k is not None else len(reranked_ids)

    recall_retrieval = _recall_at_k(retrieved_ids, gt, k)
    recall_rerank = _recall_at_k(reranked_ids, gt, k)

    relevant_in_pool = gt & set(retrieved_ids)        # rerank có cơ hội giữ
    relevant_in_output = gt & set(reranked_ids[:k])   # rerank thực sự giữ

    lost = sorted(relevant_in_pool - set(reranked_ids[:k]))
    overlap = sorted(relevant_in_output)
    gained = sorted(relevant_in_output - set(retrieved_ids[:k]))

    return {
        "query": query,
        "k": k,
        "recall_retrieval": round(recall_retrieval, 4),
        "recall_rerank": round(recall_rerank, 4),
        "recall_delta": round(recall_rerank - recall_retrieval, 4),
        "overlap_relevant": overlap,
        "lost_relevant": lost,
        "gained_rank": gained,
    }


def log_query_comparison(
    query: str,
    retrieved: list[_HasChunkId],
    reranked: list[_HasChunkId],
    ground_truth: Iterable[str],
    k: int | None = None,
    top_n: int = 10,
) -> dict:
    """In log thân thiện thử nghiệm cho một truy vấn rồi trả về dict so sánh.

    Hiển thị: top-N retrieved, top-N reranked, và chunk liên quan bị rơi.
    """
    cmp = compare_retrieval_vs_rerank(query, retrieved, reranked, ground_truth, k)
    gt = set(ground_truth)

    def _fmt(chunks: list[_HasChunkId]) -> str:
        lines = []
        for rank, c in enumerate(chunks[:top_n], start=1):
            mark = "★" if c.chunk_id in gt else " "
            snippet = (c.text or "")[:70].replace("\n", " ")
            lines.append(f"    {rank:>2}. [{mark}] {c.chunk_id}  {snippet}")
        return "\n".join(lines)

    logger.info("─" * 72)
    logger.info("QUERY: %s", query)
    logger.info("TOP-%d RETRIEVED (★ = liên quan):\n%s", top_n, _fmt(retrieved))
    logger.info("TOP-%d RERANKED  (★ = liên quan):\n%s", top_n, _fmt(reranked))
    logger.info(
        "recall@%d  retrieval=%.3f → rerank=%.3f  (Δ=%+.3f)",
        cmp["k"], cmp["recall_retrieval"], cmp["recall_rerank"], cmp["recall_delta"],
    )
    if cmp["lost_relevant"]:
        logger.warning("CHUNK LIÊN QUAN BỊ RERANK LOẠI: %s", cmp["lost_relevant"])
    if cmp["gained_rank"]:
        logger.info("CHUNK LIÊN QUAN RERANK CỨU ĐƯỢC: %s", cmp["gained_rank"])
    return cmp
