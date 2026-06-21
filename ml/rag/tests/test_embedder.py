"""
Unit tests for Embedder.

Run with: pytest tests/test_embedder.py -v
Requires sentence-transformers to be installed.
These tests load the actual model so they may be slow on first run.
Mark with @pytest.mark.slow if you want to skip them in fast CI.
"""
import pytest


@pytest.fixture(scope="module")
def embedder():
    """Create a real Embedder with a small, fast model for testing."""
    from rag.embedding.embedder import Embedder
    emb = Embedder(
        model_name="intfloat/multilingual-e5-base",
        device="cpu",      # CPU for reproducibility in CI
        batch_size=4,
        cache_size=16,
    )
    emb.load()
    return emb


class TestEmbedder:
    def test_embed_query_returns_list_of_floats(self, embedder):
        vec = embedder.embed_query("bệnh đạo ôn lá lúa")
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)

    def test_embed_query_dimension(self, embedder):
        vec = embedder.embed_query("triệu chứng bệnh rỉ sắt")
        assert len(vec) == embedder.vector_size

    def test_embed_documents_batch(self, embedder):
        texts = ["bệnh A", "bệnh B", "bệnh C"]
        vecs = embedder.embed_documents(texts)
        assert len(vecs) == 3
        assert all(len(v) == embedder.vector_size for v in vecs)

    def test_empty_documents_returns_empty(self, embedder):
        result = embedder.embed_documents([])
        assert result == []

    def test_empty_query_raises(self, embedder):
        from rag.core.exceptions import EmbeddingError
        with pytest.raises(EmbeddingError):
            embedder.embed_query("   ")

    def test_cache_deduplication(self, embedder):
        """Same text should not be re-embedded (cache hit)."""
        text = "lúa bị vàng lá tungro"
        # Warm cache
        v1 = embedder.embed_documents([text])[0]
        # Second call should hit cache
        original_encode = embedder._model.encode
        call_count = [0]

        def counting_encode(texts, **kwargs):
            call_count[0] += len(texts)
            return original_encode(texts, **kwargs)

        embedder._model.encode = counting_encode
        v2 = embedder.embed_documents([text])[0]
        embedder._model.encode = original_encode  # restore

        assert call_count[0] == 0, "Cache miss — text was re-embedded"
        assert v1 == v2

    def test_normalized_vectors_have_unit_norm(self, embedder):
        import math
        vec = embedder.embed_query("cây ngô bị rỉ sắt")
        norm = math.sqrt(sum(v ** 2 for v in vec))
        assert abs(norm - 1.0) < 1e-4, f"Expected unit norm, got {norm:.6f}"

    def test_similar_texts_have_higher_similarity(self, embedder):
        import numpy as np
        q = embedder.embed_query("bệnh rỉ sắt lúa")
        relevant = embedder.embed_documents(["Bệnh rỉ sắt trên cây lúa gây vàng lá"])[0]
        irrelevant = embedder.embed_documents(["Công thức toán học tích phân"])[0]

        def cosine(a, b):
            a, b = np.array(a), np.array(b)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

        sim_relevant = cosine(q, relevant)
        sim_irrelevant = cosine(q, irrelevant)
        assert sim_relevant > sim_irrelevant, (
            f"Expected relevant ({sim_relevant:.4f}) > irrelevant ({sim_irrelevant:.4f})"
        )
