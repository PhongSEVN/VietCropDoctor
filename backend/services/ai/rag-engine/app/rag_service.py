"""
RAG service layer — business logic for query, chat, ingest operations.

Imports updated: backend.core.state → app.state
All rag.* imports remain unchanged (rag/ package lives at rag-engine/rag/).
"""
import logging
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from rag.core.config import get_settings
from rag.core.disease_map import get_vn_name, get_crop
from rag.pipeline import RAGPipeline
from rag.utils.text import sanitize_query
from app.state import app_state

logger = logging.getLogger("rag_engine.rag_service")

_MAX_HISTORY = 5
_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=_MAX_HISTORY))

_CASUAL_RE = re.compile(
    r"^(hello|hi|hey|xin\s*ch[àa]o|ch[àa]o(\s*b[aạ]n)?|alo|ok|okay|"
    r"c[aả]m\s*[oơ]n|thanks?|thank\s+you)[!?.,\s]*$",
    re.IGNORECASE | re.UNICODE,
)


def _is_casual(text: str) -> bool:
    return bool(_CASUAL_RE.match(text.strip()))


def load_rag_chain() -> None:
    """Initialize RAG pipeline into app_state. Called once at startup."""
    try:
        settings = get_settings()
        pipeline = RAGPipeline(settings)
        pipeline.initialize()
        app_state.rag_chain = pipeline
        app_state.vectordb_connected = pipeline.qdrant.health_check()
        app_state.vectors_count = pipeline.qdrant.count()
        logger.info("[RAG] Pipeline ready | vectors=%d", app_state.vectors_count)
    except Exception as exc:
        logger.exception("[RAG] Pipeline init failed: %s", exc)


async def answer_async(
    disease: str,
    question: str,
    session_id: str = "default",
) -> tuple[str, list[str]]:
    """Backward-compat wrapper used by the /chat endpoint."""
    if app_state.rag_chain is None:
        raise RuntimeError("RAG pipeline chưa sẵn sàng")

    clean_q = sanitize_query(question)
    history = list(_history[session_id])

    disease = disease or None
    crop_filter = get_crop(disease) if disease else None
    vn_name = get_vn_name(disease) if disease else None

    if _is_casual(clean_q):
        if vn_name:
            reply = f"Xin chào! Tôi có thể giúp bạn tìm hiểu về **{vn_name}**. Bạn muốn hỏi gì về bệnh này?"
        else:
            reply = "Xin chào! Tôi có thể giúp bạn tư vấn về bệnh cây trồng. Bạn cần biết điều gì?"
        _history[session_id].append({"question": clean_q, "answer": reply})
        return reply, []

    if vn_name:
        retrieval_query = f"{vn_name} {clean_q}"
        llm_question = f"[Bệnh: {vn_name}] {clean_q}" if vn_name.lower() not in clean_q.lower() else clean_q
    else:
        retrieval_query = clean_q
        llm_question = clean_q

    response = await app_state.rag_chain.query(
        question=llm_question,
        retrieval_query=retrieval_query,
        disease_filter=crop_filter,
        history=history,
        session_id=session_id,
    )

    _history[session_id].append({"question": clean_q, "answer": response.answer})
    sources = list({c.source for c in response.chunks})
    return response.answer, sources


async def query_async(
    question: str,
    disease_filter: Optional[str] = None,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
    session_id: Optional[str] = None,
    retrieve_only: bool = False,
):
    """Full RAG query — returns QueryResponse for the /query endpoint.

    When ``retrieve_only`` is True, skip LLM generation and return only the
    retrieved/reranked chunks (used by the Orchestrator's RetrievalAgent).
    """
    from rag.models.responses import Latencies, QueryResponse
    from rag.core.config import get_settings

    if app_state.rag_chain is None:
        raise RuntimeError("RAG pipeline chưa sẵn sàng")

    clean_q = sanitize_query(question)
    history = list(_history[session_id]) if session_id else None

    crop_filter = get_crop(disease_filter) if disease_filter else None
    vn_name = get_vn_name(disease_filter) if disease_filter else None

    # Retrieve-only path (Orchestrator): return context chunks, no LLM generation.
    if retrieve_only:
        retrieval_query = f"{vn_name} {clean_q}" if vn_name else clean_q
        return await app_state.rag_chain.retrieve_chunks(
            question=clean_q,
            retrieval_query=retrieval_query,
            disease_filter=crop_filter,
            top_k=top_k,
            score_threshold=score_threshold,
            session_id=session_id,
        )

    if _is_casual(clean_q):
        if vn_name:
            reply = f"Xin chào! Tôi có thể giúp bạn tìm hiểu về **{vn_name}**. Bạn muốn hỏi gì về bệnh này?"
        else:
            reply = "Xin chào! Tôi có thể giúp bạn tư vấn về bệnh cây trồng. Bạn cần biết điều gì?"
        if session_id:
            _history[session_id].append({"question": clean_q, "answer": reply})
        zero = Latencies(embed_ms=0, retrieve_ms=0, rerank_ms=0, llm_ms=0, total_ms=0)
        return QueryResponse(
            answer=reply, chunks=[], latencies=zero,
            model=get_settings().llm_model, session_id=session_id,
        )

    if vn_name:
        retrieval_query = f"{vn_name} {clean_q}"
        llm_question = f"[Bệnh: {vn_name}] {clean_q}" if vn_name.lower() not in clean_q.lower() else clean_q
    else:
        retrieval_query = clean_q
        llm_question = clean_q

    response = await app_state.rag_chain.query(
        question=llm_question,
        retrieval_query=retrieval_query,
        disease_filter=crop_filter,
        top_k=top_k,
        score_threshold=score_threshold,
        history=history,
        session_id=session_id,
    )

    if session_id:
        _history[session_id].append({"question": clean_q, "answer": response.answer})

    return response


def ingest_directory(
    directory: Optional[str] = None,
    recreate_collection: bool = False,
) -> dict:
    """Ingest documents from directory. Returns stats dict."""
    if app_state.rag_chain is None:
        raise RuntimeError("RAG pipeline chưa sẵn sàng")

    settings = get_settings()
    dir_path = Path(directory) if directory else settings.knowledge_dir

    result = app_state.rag_chain.ingest_directory(dir_path, recreate_collection)
    app_state.vectors_count = app_state.rag_chain.qdrant.count()

    return {
        "chunks_created": result.chunks_created,
        "documents_processed": result.documents_processed,
        "collection": settings.qdrant_collection,
        "elapsed_seconds": result.elapsed_seconds,
    }


async def llm_reachable() -> bool:
    if app_state.rag_chain is None:
        return False
    return await app_state.rag_chain.llm.health_check()


def clear_session(session_id: str) -> None:
    _history.pop(session_id, None)
