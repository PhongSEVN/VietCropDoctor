"""
Thuật toán chia văn bản (chunking) theo phương pháp đệ quy.

Chiến lược chia (ưu tiên từ thô đến mịn):
  1. Tách theo đoạn văn (dòng trống \n\n) — giữ nguyên ý nghĩa nhất.
  2. Nếu đoạn vẫn quá dài → tách theo dòng đơn (\n).
  3. Tiếp tục tách theo dấu câu kết thúc câu (". ", "! ", "? ").
  4. Tách theo dấu phân cách nhỏ hơn ("; ", ", ").
  5. Tách theo khoảng trắng (từng từ).
  6. Cuối cùng: tách thô theo ký tự (hard cut) nếu không còn cách nào.

Phương pháp này tương đương RecursiveCharacterTextSplitter của LangChain
nhưng không phụ thuộc thư viện ngoài và kiểm soát rõ ràng cửa sổ overlap.

Ví dụ (chunk_size=20, overlap=5):
  Văn bản gốc: "AAAAAAAAAA BBBBBBBBBB CCCCCCCCCC"
  Chunk 1:     "AAAAAAAAAA BBBBB"        ← 20 ký tự
  Chunk 2:          "BBBBB CCCCCCCCCC"   ← bắt đầu từ overlap của chunk 1
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from rag.ingestion.loader import Document

logger = logging.getLogger(__name__)

# Danh sách ký tự phân tách, sắp xếp từ đơn vị ngữ nghĩa lớn → nhỏ.
# Thuật toán thử từ trên xuống, dừng lại khi tìm được separator
# tạo ra các piece đủ nhỏ (≤ chunk_size).
_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]


@dataclass
class DocumentChunk:
    """Một đoạn văn bản đã được chia, sẵn sàng để embedding."""

    chunk_id: str        # ID duy nhất, tính từ sha256(source + index + text prefix)
    text: str            # Nội dung văn bản của chunk
    source: str          # Đường dẫn file gốc
    filename: str        # Tên file
    chunk_index: int     # Thứ tự chunk trong document (bắt đầu từ 0)
    chunk_total: int     # Tổng số chunk của document gốc
    timestamp: str       # Thời điểm tạo chunk (ISO 8601 UTC)
    metadata: dict = field(default_factory=dict)  # Metadata kế thừa từ document (crop, disease_name, ...)


class RecursiveTextChunker:
    """Chia document thành các chunk có overlap, ưu tiên giữ ranh giới ngữ nghĩa.

    Thuật toán hoạt động đệ quy:
    - Thử tách bằng separator thô nhất (\n\n) trước.
    - Nếu piece nào vẫn > chunk_size → đệ quy với separator mịn hơn.
    - Các piece đủ nhỏ được gộp lại thành cửa sổ chunk_size với overlap.

    Args:
        chunk_size:     Số ký tự tối đa mỗi chunk (mặc định 512).
        chunk_overlap:  Số ký tự lặp lại giữa 2 chunk liền kề (mặc định 64).
        min_chunk_size: Bỏ qua chunk ngắn hơn ngưỡng này (mặc định 80).
        separators:     Ghi đè danh sách separator mặc định.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        min_chunk_size: int = 80,
        separators: Optional[list[str]] = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.separators = separators or _SEPARATORS

    # API công khai
    def chunk_document(self, doc: Document) -> list[DocumentChunk]:
        """Chia một Document thành danh sách chunk kèm metadata."""
        pieces = self._recursive_split(doc.text, self.separators)
        # Lọc bỏ các piece quá ngắn (không đủ context để embedding có nghĩa)
        pieces = [p.strip() for p in pieces if len(p.strip()) >= self.min_chunk_size]

        if not pieces:
            logger.warning("Document không tạo ra chunk nào: %s", doc.filename)
            return []

        ts = datetime.now(timezone.utc).isoformat()
        chunks: list[DocumentChunk] = []

        for idx, text in enumerate(pieces):
            chunk_id = _make_chunk_id(doc.source, idx, text)
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    text=text,
                    source=doc.source,
                    filename=doc.filename,
                    chunk_index=idx,
                    chunk_total=len(pieces),
                    timestamp=ts,
                    metadata={
                        **doc.extra_metadata,
                        "doc_type": doc.doc_type,
                    },
                )
            )

        return chunks

    def chunk_documents(self, docs: list[Document]) -> list[DocumentChunk]:
        """Chia nhiều document, trả về danh sách chunk phẳng (flat list)."""
        all_chunks: list[DocumentChunk] = []
        for doc in docs:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)
            logger.debug("  %s → %d chunks", doc.filename, len(chunks))
        logger.info("Tổng chunk tạo ra: %d từ %d documents", len(all_chunks), len(docs))
        return all_chunks

    # Hàm nội bộ

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """
        Tách `text` bằng separator phù hợp đầu tiên trong danh sách.

        Với mỗi separator (từ thô đến mịn):
        - Nếu text chứa separator → tách → gộp lại thành cửa sổ overlap.
        - Piece nào vẫn > chunk_size → đệ quy với các separator còn lại (mịn hơn).
        - Nếu tất cả separator đều thất bại → hard cut theo ký tự.
        """
        # Nếu text đã đủ nhỏ, không cần tách thêm
        if len(text) <= self.chunk_size:
            return [text]

        for i, sep in enumerate(separators):
            if sep == "":
                # Không còn separator nào → tách thô theo ký tự
                return self._character_split(text)

            if sep not in text:
                # Separator này không có trong text → thử cái tiếp theo
                continue

            # Tách theo separator hiện tại, gộp lại thành cửa sổ có overlap
            raw_pieces = text.split(sep)
            merged = self._merge_with_overlap(raw_pieces, sep)

            # Xử lý đệ quy các piece vẫn còn quá lớn
            result: list[str] = []
            for piece in merged:
                if len(piece) > self.chunk_size:
                    # Piece quá lớn → đệ quy với separator mịn hơn
                    result.extend(
                        self._recursive_split(piece, separators[i + 1:])
                    )
                else:
                    result.append(piece)
            return result

        return [text]

    def _merge_with_overlap(self, pieces: list[str], sep: str) -> list[str]:
        """
        Gộp các piece đã tách thành cửa sổ ≤ chunk_size ký tự,
        duy trì buffer overlap chunk_overlap ký tự giữa 2 chunk liền kề.

        Cách hoạt động:
        - Duyệt từng piece, cộng dồn vào cửa sổ hiện tại (current).
        - Khi cửa sổ đầy (> chunk_size) → emit chunk, giữ lại phần đuôi
          làm overlap cho chunk tiếp theo (xoá từ đầu cho đến khi
          current_len ≤ chunk_overlap).
        """
        chunks: list[str] = []
        current: list[str] = []   # Các piece đang gộp vào chunk hiện tại
        current_len: int = 0      # Tổng ký tự trong current (tính cả separator)
        sep_len = len(sep)

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue

            # Độ dài khi thêm piece này vào current
            addition = sep_len + len(piece) if current else len(piece)

            if current_len + addition > self.chunk_size and current:
                # Cửa sổ đầy → emit chunk hiện tại
                chunks.append(sep.join(current))

                # Xoá từ đầu current cho đến khi còn lại ≤ chunk_overlap ký tự
                # (phần còn lại này sẽ là overlap đầu chunk tiếp theo)
                while current and current_len > self.chunk_overlap:
                    removed = current.pop(0)
                    current_len -= len(removed) + sep_len
                    if current_len < 0:
                        current_len = 0

            current.append(piece)
            current_len += addition

        # Emit phần còn lại (chunk cuối)
        if current:
            chunks.append(sep.join(current))

        return chunks

    def _character_split(self, text: str) -> list[str]:
        """
        Tách thô theo ký tự khi không còn separator ngữ nghĩa nào dùng được.
        Mỗi chunk bước nhảy step = chunk_size - chunk_overlap để duy trì overlap.
        """
        step = max(1, self.chunk_size - self.chunk_overlap)
        return [
            text[i: i + self.chunk_size]
            for i in range(0, len(text), step)
            if len(text[i: i + self.chunk_size]) >= self.min_chunk_size
        ]


def _make_chunk_id(source: str, index: int, text: str) -> str:
    """
    Tạo chunk ID xác định (deterministic) từ đường dẫn source, thứ tự index,
    và 64 ký tự đầu của text.

    Dùng sha256 → cắt 16 ký tự hex.
    Deterministic = ingest lại cùng file không tạo ID mới → Qdrant không bị trùng vector.
    """
    key = f"{source}::{index}::{text[:64]}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]