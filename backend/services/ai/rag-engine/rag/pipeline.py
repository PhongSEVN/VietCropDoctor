"""
RAG pipeline orchestrator.

Wires together all RAG components and exposes two high-level operations:
  • ingest(docs)  — load → clean → chunk → embed → upsert
  • query(...)    — embed → retrieve → rerank → prompt → generate

The pipeline owns no framework-specific state; it is a plain Python class
that can be unit-tested independently of FastAPI.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from rag.core.config import Settings
from rag.models.responses import Latencies, QueryResponse, RetrievedChunk
from rag.embedding.embedder import Embedder
from rag.generation.llm_service import BaseLLMService, OllamaLLMService
from rag.generation.prompt_builder import format_no_context_answer
from rag.ingestion.chunker import DocumentChunk, RecursiveTextChunker
from rag.ingestion.cleaner import TextCleaner
from rag.ingestion.loader import Document, DocumentLoader
from rag.reranking.reranker import Reranker
from rag.retrieval.retriever import Retriever
from rag.vectorstore.qdrant_service import QdrantService
from rag.utils.timing import Timer, timed

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    chunks_created: int
    documents_processed: int
    elapsed_seconds: float


class RAGPipeline:
    """Full RAG pipeline: ingest and query.

    All components are injected so they can be replaced for testing.
    Call ``initialize()`` once before using.

    Args:
        settings: Application settings.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ready = False

        # Components (initialised lazily in initialize())
        self.loader = DocumentLoader()
        self.cleaner = TextCleaner()
        self.chunker = RecursiveTextChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            min_chunk_size=settings.chunk_min_size,
        )
        self.embedder = Embedder(
            model_name=settings.embedding_model,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
            max_length=settings.embedding_max_length,
            normalize=settings.embedding_normalize,
            cache_size=settings.embedding_cache_size,
        )
        self.qdrant = QdrantService(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=settings.qdrant_collection,
            vector_size=settings.embedding_vector_size,
            timeout=settings.qdrant_timeout,
            upsert_batch_size=settings.qdrant_upsert_batch_size,
        )
        self._dense_retriever = Retriever(
            embedder=self.embedder,
            qdrant=self.qdrant,
            top_k=settings.retrieval_top_k,
            score_threshold=settings.retrieval_score_threshold,
            multi_query=settings.retrieval_multi_query,
            multi_query_count=settings.retrieval_multi_query_count,
        )
        # Active retriever — replaced by HybridRetriever in initialize() when
        # hybrid_retrieval=True and a BM25 index is available on disk.
        self.retriever = self._dense_retriever
        self.reranker = Reranker(
            model_name=settings.reranker_model,
            top_k=settings.reranker_top_k,
            enabled=settings.reranker_enabled,
        )
        self.llm: BaseLLMService = OllamaLLMService(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )

    # Lifecycle

    def initialize(self) -> None:
        """Warmup all components. Call once at app startup."""
        if self._ready:
            return
        logger.info("Initialising RAG pipeline…")
        self.qdrant.ensure_collection()
        self.embedder.load()
        self.reranker.load()

        if self.settings.hybrid_retrieval:
            self._try_load_bm25()

        self._ready = True
        logger.info("RAG pipeline ready.")

    def _try_load_bm25(self) -> None:
        """Attempt to load a persisted BM25 index and activate HybridRetriever."""
        from pathlib import Path
        from rag.retrieval.bm25_retriever import BM25Retriever
        from rag.retrieval.hybrid_retriever import HybridRetriever

        bm25_path = Path(self.settings.bm25_index_path)
        if not bm25_path.exists():
            logger.info(
                "No BM25 index at '%s' — using dense-only retrieval. "
                "Trigger /reindex to build the hybrid index.",
                bm25_path,
            )
            return
        try:
            bm25 = BM25Retriever.load(bm25_path)
            self.retriever = HybridRetriever(
                dense=self._dense_retriever,
                bm25=bm25,
                alpha=self.settings.hybrid_alpha,
            )
            logger.info(
                "Hybrid retrieval enabled | alpha=%.2f bm25_chunks=%d",
                self.settings.hybrid_alpha, len(bm25),
            )
        except Exception as exc:
            logger.warning(
                "Could not load BM25 index ('%s'): %s — falling back to dense retrieval.",
                bm25_path, exc,
            )

    def shutdown(self) -> None:
        """Release GPU resources."""
        self.embedder.unload()
        logger.info("RAG pipeline shut down.")

    # Ingestion

    def ingest_documents(
        self,
        docs: list[Document],
        recreate_collection: bool = False,
    ) -> IngestResult:
        """Clean, chunk, embed, and upsert a list of Documents.

        Args:
            docs:               Pre-loaded Documents.
            recreate_collection: Drop and recreate Qdrant collection first.

        Returns:
            IngestResult with counts and elapsed time.
        """
        import time
        start = time.perf_counter()

        if recreate_collection:
            self.qdrant.recreate_collection()
            logger.info("Collection recreated before ingestion.")

        logger.info("Starting ingestion of %d documents.", len(docs))

        # Clean
        cleaned = self.cleaner.clean_batch(docs)

        # Chunk
        chunks: list[DocumentChunk] = self.chunker.chunk_documents(cleaned)
        if not chunks:
            logger.warning("No chunks produced from %d documents.", len(docs))
            return IngestResult(0, len(docs), time.perf_counter() - start)

        # Embed
        logger.info("Embedding %d chunks…", len(chunks))
        texts = [c.text for c in chunks]
        vectors = self.embedder.embed_documents(texts)
        logger.info("Embedding complete.")

        # Build payloads
        payloads = [
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "source": c.source,
                "filename": c.filename,
                "chunk_index": c.chunk_index,
                "chunk_total": c.chunk_total,
                "timestamp": c.timestamp,
                **c.metadata,
            }
            for c in chunks
        ]
        ids = [c.chunk_id for c in chunks]

        # Upsert
        self.qdrant.upsert(vectors=vectors, payloads=payloads, ids=ids)

        elapsed = time.perf_counter() - start
        logger.info(
            "Ingestion complete | docs=%d chunks=%d elapsed=%.1fs",
            len(docs), len(chunks), elapsed,
        )

        # Rebuild BM25 index so hybrid retrieval reflects the new corpus.
        if self.settings.hybrid_retrieval:
            try:
                self.rebuild_bm25_index()
            except Exception:
                logger.warning("BM25 rebuild failed — hybrid retrieval may be stale.", exc_info=True)

        return IngestResult(
            chunks_created=len(chunks),
            documents_processed=len(docs),
            elapsed_seconds=round(elapsed, 2),
        )

    def rebuild_bm25_index(self) -> None:
        """Scroll all chunks from Qdrant and rebuild the BM25 index on disk.

        After building, replaces ``self.retriever`` with a new HybridRetriever
        backed by the freshly built index.  No-op if the collection is empty.
        """
        from pathlib import Path
        from rag.retrieval.bm25_retriever import BM25Retriever
        from rag.retrieval.hybrid_retriever import HybridRetriever

        logger.info("Rebuilding BM25 index from Qdrant…")
        raw = self.qdrant.scroll_all()
        if not raw:
            logger.warning("Qdrant collection is empty — BM25 index not built.")
            return

        corpus   = [r["text"]     for r in raw]
        chunk_ids = [r["chunk_id"] for r in raw]

        bm25 = BM25Retriever(corpus=corpus, chunk_ids=chunk_ids)

        index_path = Path(self.settings.bm25_index_path)
        bm25.save(index_path)

        self.retriever = HybridRetriever(
            dense=self._dense_retriever,
            bm25=bm25,
            alpha=self.settings.hybrid_alpha,
        )
        logger.info(
            "BM25 index rebuilt | chunks=%d path=%s alpha=%.2f",
            len(raw), index_path, self.settings.hybrid_alpha,
        )

    def ingest_directory(
        self,
        directory_path,
        recreate_collection: bool = False,
    ) -> IngestResult:
        """Load all documents from a directory and ingest them."""
        from pathlib import Path
        docs = self.loader.load_directory(Path(directory_path))
        return self.ingest_documents(docs, recreate_collection=recreate_collection)

    # Query

    async def query(
        self,
        question: str,
        disease_filter: Optional[str] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        history: Optional[list[dict[str, str]]] = None,
        session_id: Optional[str] = None,
        retrieval_query: Optional[str] = None,
    ) -> QueryResponse:
        """Full RAG query: retrieve → rerank → generate.

        Args:
            question:        Sanitised user question.
            disease_filter:  Optional disease class label for scoped retrieval.
            top_k:           Override retrieval top_k.
            score_threshold: Override score threshold.
            history:         Conversation history (question/answer dicts).
            session_id:      Passed through to response.

        Returns:
            QueryResponse with answer, chunks, and latencies.
        """
        timer = Timer()
        # Use retrieval_query for embedding/search if provided (allows
        # keyword-focused queries while the LLM sees the original question)
        _ret_q = retrieval_query or question

        # 1. Retrieve — khi bật rerank, lấy POOL lớn (rerank_candidate_k) để
        # cross-encoder có đủ ứng viên; nếu không rerank thì lấy đúng số cuối.
        if top_k is not None:
            retrieve_k = top_k
        elif self.reranker.enabled:
            retrieve_k = self.settings.rerank_candidate_k
        else:
            retrieve_k = self.settings.retrieval_top_k

        with timed(timer, "retrieve_ms"):
            import time as _time
            t0 = _time.perf_counter()
            # to_thread: embedding là CPU-bound (sentence-transformers) — chạy
            # sync sẽ chặn event loop, treo /health và mọi request khác.
            query_vec = await asyncio.to_thread(self.embedder.embed_query, _ret_q)
            timer.record("embed_ms", (_time.perf_counter() - t0) * 1000)

            candidates = await self.retriever.retrieve(
                query=_ret_q,
                top_k=retrieve_k,
                score_threshold=score_threshold,
                disease_filter=disease_filter,
            )

        # 2. Rerank — thu pool về reranker_top_k chunk đưa vào LLM.
        with timed(timer, "rerank_ms"):
            # to_thread: cross-encoder chấm 30 cặp trên CPU có thể mất nhiều
            # giây khi Ollama đang chiếm CPU — không được chặn event loop.
            chunks = await asyncio.to_thread(self.reranker.rerank, question, candidates)

        # 3. Generate
        if not chunks:
            answer = format_no_context_answer()
            timer.record("llm_ms", 0.0)
            logger.info("No relevant chunks found for query '%s'.", question[:60])
        else:
            with timed(timer, "llm_ms"):
                answer = await self.llm.generate(
                    question=question,
                    chunks=chunks,
                    history=history,
                )

        latencies = Latencies(
            embed_ms=timer.get("embed_ms"),
            retrieve_ms=round(timer.get("retrieve_ms") - timer.get("embed_ms"), 2),
            rerank_ms=timer.get("rerank_ms"),
            llm_ms=timer.get("llm_ms"),
            total_ms=timer.total_ms(),
        )

        logger.info(
            "Query complete | chunks=%d answer_len=%d total=%.0fms",
            len(chunks), len(answer), latencies.total_ms,
        )

        return QueryResponse(
            answer=answer,
            chunks=chunks,
            latencies=latencies,
            model=self.settings.llm_model,
            session_id=session_id,
        )

    async def retrieve_chunks(
        self,
        question: str,
        disease_filter: Optional[str] = None,
        top_k: Optional[int] = None,
        score_threshold: Optional[float] = None,
        session_id: Optional[str] = None,
        retrieval_query: Optional[str] = None,
    ) -> QueryResponse:
        """Retrieve → rerank only, skipping LLM generation.

        Used by the Orchestrator (RetrievalAgent), which feeds the retrieved
        chunks as context into its own reasoning LLM call. Returning context
        instead of a generated answer avoids a redundant second LLM invocation.
        Mirrors steps 1–2 of ``query`` and returns ``answer=""``.
        """
        import time as _time

        timer = Timer()
        _ret_q = retrieval_query or question

        if top_k is not None:
            retrieve_k = top_k
        elif self.reranker.enabled:
            retrieve_k = self.settings.rerank_candidate_k
        else:
            retrieve_k = self.settings.retrieval_top_k

        with timed(timer, "retrieve_ms"):
            t0 = _time.perf_counter()
            await asyncio.to_thread(self.embedder.embed_query, _ret_q)
            timer.record("embed_ms", (_time.perf_counter() - t0) * 1000)

            candidates = await self.retriever.retrieve(
                query=_ret_q,
                top_k=retrieve_k,
                score_threshold=score_threshold,
                disease_filter=disease_filter,
            )

        with timed(timer, "rerank_ms"):
            chunks = await asyncio.to_thread(self.reranker.rerank, question, candidates)

        timer.record("llm_ms", 0.0)
        latencies = Latencies(
            embed_ms=timer.get("embed_ms"),
            retrieve_ms=round(timer.get("retrieve_ms") - timer.get("embed_ms"), 2),
            rerank_ms=timer.get("rerank_ms"),
            llm_ms=0.0,
            total_ms=timer.total_ms(),
        )

        logger.info("Retrieve-only complete | chunks=%d total=%.0fms", len(chunks), latencies.total_ms)

        return QueryResponse(
            answer="",
            chunks=chunks,
            latencies=latencies,
            model=self.settings.llm_model,
            session_id=session_id,
        )
