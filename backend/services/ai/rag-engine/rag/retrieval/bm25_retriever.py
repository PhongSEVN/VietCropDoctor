"""
BM25 sparse retriever.

Dùng rank_bm25.BM25Okapi để tìm kiếm theo từ khoá.
Chỉ mục được xây dựng trên toàn bộ corpus khi khởi tạo và có thể
serialize ra đĩa bằng pickle để dùng lại sau khi khởi động lại.

Tokenize đơn giản: lowercase + tách khoảng trắng — đủ dùng cho văn bản
bệnh cây trồng tiếng Việt và tránh phụ thuộc thư viện NLP nặng.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


class BM25Retriever:
    """Sparse BM25 retriever sử dụng rank_bm25.BM25Okapi.

    Args:
        corpus:    Danh sách văn bản tài liệu (một phần tử mỗi chunk).
        chunk_ids: Danh sách chunk ID tương ứng song song với corpus.
    """

    def __init__(self, corpus: list[str], chunk_ids: list[str]) -> None:
        if len(corpus) != len(chunk_ids):
            raise ValueError("corpus và chunk_ids phải có cùng độ dài.")

        self._chunk_ids: list[str] = list(chunk_ids)
        self._id_to_text: dict[str, str] = dict(zip(chunk_ids, corpus))

        tokenized = [_tokenize(doc) for doc in corpus]
        self._bm25 = BM25Okapi(tokenized)

        logger.debug("BM25Retriever đã xây dựng | corpus_size=%d", len(corpus))

    # Search
    def search(self, query: str, top_k: int) -> list[dict]:
        """Trả về top-k chunk liên quan nhất với câu hỏi.

        Args:
            query:  Chuỗi câu hỏi thô (sẽ được tokenize bên trong).
            top_k:  Số lượng kết quả tối đa.

        Returns:
            Danh sách dict với các key ``chunk_id``, ``score``, ``rank`` (đánh số từ 1).
            Trả về danh sách rỗng nếu corpus trống hoặc không có tài liệu nào có điểm > 0.
        """
        if not self._chunk_ids:
            return []

        tokens = _tokenize(query)
        scores: list[float] = self._bm25.get_scores(tokens).tolist()

        # Ghép (score, chunk_id) và sắp xếp giảm dần
        indexed = sorted(
            zip(scores, self._chunk_ids),
            key=lambda x: x[0],
            reverse=True,
        )

        results = []
        for rank, (score, chunk_id) in enumerate(indexed[:top_k], start=1):
            if score <= 0:
                break
            results.append({"chunk_id": chunk_id, "score": score, "rank": rank})

        logger.debug(
            "BM25 search | query='%s' hits=%d", query[:60], len(results)
        )
        return results

    def get_text(self, chunk_id: str) -> str:
        """Trả về văn bản thô của chunk_id, hoặc chuỗi rỗng nếu không tìm thấy."""
        return self._id_to_text.get(chunk_id, "")

    # Persistence
    def save(self, path: Path) -> None:
        """Lưu retriever ra file bằng pickle."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("BM25 index đã lưu → %s (%d chunks)", path, len(self._chunk_ids))

    @classmethod
    def load(cls, path: Path) -> "BM25Retriever":
        """Khôi phục BM25Retriever từ file pickle.

        Raises:
            FileNotFoundError: nếu file không tồn tại.
            RuntimeError:      nếu không thể unpickle file.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"BM25 index không tìm thấy tại {path}")
        try:
            with path.open("rb") as f:
                obj = pickle.load(f)
            if not isinstance(obj, cls):
                raise RuntimeError(
                    f"Object được pickle là {type(obj)}, expected BM25Retriever"
                )
            logger.info("BM25 index đã tải ← %s (%d chunks)", path, len(obj._chunk_ids))
            return obj
        except (pickle.UnpicklingError, Exception) as exc:
            raise RuntimeError(f"Không thể tải BM25 index: {exc}") from exc

    # Info

    def __len__(self) -> int:
        return len(self._chunk_ids)

    def __repr__(self) -> str:
        return f"BM25Retriever(corpus_size={len(self._chunk_ids)})"
