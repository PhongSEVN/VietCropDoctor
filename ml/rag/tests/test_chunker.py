"""
Unit tests for RecursiveTextChunker.

Run with: pytest tests/test_chunker.py -v
"""
import pytest

from rag.ingestion.chunker import RecursiveTextChunker, _make_chunk_id
from rag.ingestion.loader import Document


def _make_doc(text: str, filename: str = "test.txt") -> Document:
    return Document(
        text=text,
        source=f"rag/knowledge/test/{filename}",
        filename=filename,
        doc_type="txt",
    )


class TestRecursiveTextChunker:
    def setup_method(self):
        self.chunker = RecursiveTextChunker(
            chunk_size=200,
            chunk_overlap=30,
            min_chunk_size=20,
        )

    def test_short_document_produces_one_chunk(self):
        doc = _make_doc("Bệnh đạo ôn là bệnh nguy hiểm nhất trên lúa.")
        chunks = self.chunker.chunk_document(doc)
        assert len(chunks) == 1
        assert chunks[0].text == doc.text

    def test_long_document_produces_multiple_chunks(self):
        long_text = "Đây là đoạn văn bản dài để kiểm tra chunker. " * 20
        doc = _make_doc(long_text)
        chunks = self.chunker.chunk_document(doc)
        assert len(chunks) > 1

    def test_chunk_size_respected(self):
        long_text = "A" * 1000
        doc = _make_doc(long_text)
        chunks = self.chunker.chunk_document(doc)
        for chunk in chunks:
            assert len(chunk.text) <= self.chunker.chunk_size + 10  # small tolerance

    def test_metadata_is_propagated(self):
        doc = _make_doc("Triệu chứng: lá vàng.")
        doc.extra_metadata = {"crop": "lúa", "disease_name": "Đạo ôn"}
        chunks = self.chunker.chunk_document(doc)
        assert chunks[0].metadata["crop"] == "lúa"
        assert chunks[0].metadata["disease_name"] == "Đạo ôn"

    def test_chunk_ids_are_unique(self):
        long_text = ("Bệnh đốm nâu do nấm gây ra. " * 30)
        doc = _make_doc(long_text)
        chunks = self.chunker.chunk_document(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"

    def test_chunk_indices_are_sequential(self):
        long_text = "Paragraph.\n\n" * 20
        doc = _make_doc(long_text)
        chunks = self.chunker.chunk_document(doc)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_document_returns_empty_list(self):
        doc = _make_doc("   \n\n  ")
        chunks = self.chunker.chunk_document(doc)
        assert chunks == []

    def test_chunk_total_is_correct(self):
        long_text = "X " * 500
        doc = _make_doc(long_text)
        chunks = self.chunker.chunk_document(doc)
        total = len(chunks)
        for c in chunks:
            assert c.chunk_total == total

    def test_paragraph_separator_is_preferred(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        doc = _make_doc(text)
        chunker = RecursiveTextChunker(chunk_size=50, chunk_overlap=5, min_chunk_size=5)
        chunks = chunker.chunk_document(doc)
        # Each paragraph is short; they should each be their own chunk
        texts = [c.text for c in chunks]
        assert any("Paragraph one" in t for t in texts)
        assert any("Paragraph two" in t for t in texts)


class TestChunkId:
    def test_same_inputs_produce_same_id(self):
        id1 = _make_chunk_id("source.txt", 0, "hello world")
        id2 = _make_chunk_id("source.txt", 0, "hello world")
        assert id1 == id2

    def test_different_source_different_id(self):
        id1 = _make_chunk_id("a.txt", 0, "hello")
        id2 = _make_chunk_id("b.txt", 0, "hello")
        assert id1 != id2

    def test_id_is_hex_string(self):
        chunk_id = _make_chunk_id("test.txt", 1, "text")
        assert all(c in "0123456789abcdef" for c in chunk_id)
