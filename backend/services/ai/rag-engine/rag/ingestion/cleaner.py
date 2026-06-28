"""
Làm sạch văn bản cho pipeline nạp.

Áp dụng chuẩn hóa unicode, loại bỏ ký tự điều khiển và co lại khoảng trắng trước khi chia chunk.
"""
from __future__ import annotations

from rag.ingestion.loader import Document
from rag.utils.text import clean_text


class TextCleaner:
    """Áp dụng làm sạch văn bản xác định cho Document objects.
    Được thiết kế để không trạng thái và không có tác dụng phụ để có thể được sử dụng trong các pipeline nạp song song.
    """

    def clean(self, doc: Document) -> Document:
        """Trả về một Document mới với văn bản đã làm sạch (bản gốc không bị thay đổi)."""
        cleaned = clean_text(doc.text)
        return Document(
            text=cleaned,
            source=doc.source,
            filename=doc.filename,
            doc_type=doc.doc_type,
            extra_metadata=doc.extra_metadata.copy(),
        )

    def clean_batch(self, docs: list[Document]) -> list[Document]:
        """Làm sạch một danh sách các tài liệu."""
        return [self.clean(doc) for doc in docs]
