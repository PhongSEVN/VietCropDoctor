"""
RAG Engine microservice — FastAPI entry point.

Endpoints: /query  /chat  /ingest  /reindex  /ingest/upload
           /collection  /health
"""
import asyncio
import json
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import os

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from prometheus_fastapi_instrumentator import Instrumentator

from vcd_shared.kafka import (
    TOPIC_CHAT_REQUESTED,
    TOPIC_DISEASE_DETECTED,
    TOPIC_FEEDBACK_SUBMITTED,
    KafkaConsumer,
    KafkaProducer,
)
from vcd_shared.logging import setup_logging
from vcd_shared.schemas import (
    ChatRequest, ChatResponse,
    CollectionStatsResponse,
    FeedbackItem, FeedbackRequest, FeedbackResponse,
    HealthResponse,
    IngestDirectoryRequest, IngestResponse,
    QueryRequest, QueryResponse,
)
from app import database as db
from app import feedback_minio
from app import rag_service
from app.metrics import chunks_retrieved, rag_latency, rag_queries_total
from app.state import app_state
from rag.core.config import get_settings
from rag.core.exceptions import LLMUnavailableError, VectorStoreError

_ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".pdf", ".json"}

logger = logging.getLogger("rag_engine.main")

_JWT_SECRET    = os.getenv("JWT_SECRET", "change-me-in-production-use-64-char-random")
_JWT_ALGORITHM = "HS256"
_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _user_id_from_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return ""
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        return str(payload.get("sub", ""))
    except JWTError:
        return ""


_producer: KafkaProducer | None = None
_consumer_task: asyncio.Task | None = None


async def _on_disease_detected(message: dict) -> None:
    payload = message.get("payload", {})
    logger.info(
        "Received disease.detected event: disease=%s confidence=%.3f",
        payload.get("disease"),
        payload.get("confidence", 0.0),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _producer, _consumer_task

    settings = get_settings()
    setup_logging(level=settings.log_level)
    logger.info("=" * 55)
    logger.info("Starting VietCropDoctor RAG Engine")
    logger.info("=" * 55)
    rag_service.load_rag_chain()

    try:
        await db.init_pool()
    except Exception:
        logger.warning("PostgreSQL unavailable — chat history will not be persisted")

    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")

    _producer = KafkaProducer(bootstrap_servers=bootstrap, service="rag-engine")
    try:
        await _producer.start()
    except Exception:
        logger.warning("Kafka producer unavailable — chat events will not be published")
        _producer = None

    try:
        consumer = KafkaConsumer(
            bootstrap_servers=bootstrap,
            topics=[TOPIC_DISEASE_DETECTED],
            group_id="rag-engine-group",
        )
        consumer.subscribe(_on_disease_detected)
        _consumer_task = asyncio.create_task(consumer.start())
    except Exception:
        logger.warning("Kafka consumer unavailable — disease events will not be consumed")
        _consumer_task = None

    logger.info("RAG Engine ready.")
    yield
    logger.info("RAG Engine shutting down.")

    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass

    if _producer:
        await _producer.stop()

    if app_state.rag_chain is not None:
        app_state.rag_chain.shutdown()

    await db.close_pool()


app = FastAPI(
    title="VietCropDoctor RAG Engine",
    version="1.0.0",
    description="Retrieval-Augmented Generation service for Vietnamese crop disease Q&A",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

from app.expert_routes import router as expert_router  # noqa: E402
app.include_router(expert_router)


# Health

@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health():
    return HealthResponse(
        status="ok",
        vectordb_connected=app_state.vectordb_connected,
        llm_reachable=await rag_service.llm_reachable(),
        vectors_count=app_state.vectors_count,
    )


# Chat

@app.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(req: ChatRequest):
    try:
        answer_text, sources = await rag_service.answer_async(
            req.disease, req.question, req.session_id
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ChatResponse(answer=answer_text, sources=sources)


# Query

@app.post("/query", response_model=QueryResponse, tags=["query"])
async def query(
    req: QueryRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """Full RAG query with chunks, scores, and latencies."""
    if req.stream:
        return await _stream_query(req)
    try:
        response = await rag_service.query_async(
            question=req.question,
            disease_filter=req.disease_filter,
            top_k=req.top_k,
            score_threshold=req.score_threshold,
            session_id=req.session_id,
            retrieve_only=req.retrieve_only,
        )
    except (RuntimeError, LLMUnavailableError, VectorStoreError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(exc))

    # Retrieve-only requests (Orchestrator context fetch) produce no answer to
    # persist and represent no end-user chat turn — return chunks directly.
    if req.retrieve_only:
        return response

    effective_user_id = x_user_id or _user_id_from_token(authorization)
    if effective_user_id and req.session_id:
        import asyncio
        asyncio.create_task(db.save_chat_message(
            user_id=effective_user_id,
            session_id=req.session_id,
            disease=req.disease_filter,
            question=req.question,
            answer=response.answer,
            image_url=req.image_url,
        ))

    if _producer:
        try:
            await _producer.publish(
                topic=TOPIC_CHAT_REQUESTED,
                event_type="chat.requested",
                payload={
                    "question": req.question,
                    "disease_filter": req.disease_filter,
                    "session_id": req.session_id,
                },
            )
        except Exception:
            logger.warning("Failed to publish chat.requested event", exc_info=True)

    # Record Prometheus metrics.
    crop = (req.disease_filter or "all").split("_")[0].lower()
    rag_queries_total.labels(crop=crop).inc()
    if response.latencies:
        lat = response.latencies
        for stage, ms in [
            ("embed",    lat.embed_ms),
            ("retrieve", lat.retrieve_ms),
            ("rerank",   lat.rerank_ms),
            ("llm",      lat.llm_ms),
        ]:
            rag_latency.labels(stage=stage).observe(ms / 1000.0)
    chunks_retrieved.observe(len(response.chunks))

    return response


async def _stream_query(req: QueryRequest):
    from rag.utils.text import sanitize_query
    from rag.core.disease_map import get_crop, get_vn_name
    from rag.generation.prompt_builder import format_no_context_answer
    import time

    async def event_generator():
        if app_state.rag_chain is None:
            yield f"data: {json.dumps({'error': 'RAG pipeline not ready'})}\n\n"
            return

        clean_q = sanitize_query(req.question)
        pipeline = app_state.rag_chain

        crop_filter = get_crop(req.disease_filter) if req.disease_filter else None
        vn_name = get_vn_name(req.disease_filter) if req.disease_filter else None
        if vn_name:
            retrieval_query = f"{vn_name} {clean_q}"
            llm_question = (
                f"[Bệnh: {vn_name}] {clean_q}"
                if vn_name.lower() not in clean_q.lower()
                else clean_q
            )
        else:
            retrieval_query = clean_q
            llm_question = clean_q

        try:
            t0 = time.perf_counter()
            pipeline.embedder.embed_query(retrieval_query)
            embed_ms = (time.perf_counter() - t0) * 1000

            candidates = await pipeline.retriever.retrieve(
                query=retrieval_query,
                top_k=req.top_k,
                score_threshold=req.score_threshold,
                disease_filter=crop_filter,
            )
            retrieve_ms = (time.perf_counter() - t0) * 1000 - embed_ms

            t_rerank = time.perf_counter()
            chunks = pipeline.reranker.rerank(llm_question, candidates)
            rerank_ms = (time.perf_counter() - t_rerank) * 1000

            if not chunks:
                yield f"data: {json.dumps({'token': format_no_context_answer()})}\n\n"
            else:
                t_llm = time.perf_counter()
                async for token in pipeline.llm.stream_generate(question=llm_question, chunks=chunks):
                    yield f"data: {json.dumps({'token': token})}\n\n"
                llm_ms = (time.perf_counter() - t_llm) * 1000
                total_ms = embed_ms + retrieve_ms + rerank_ms + llm_ms
                done = {
                    "done": True,
                    "chunks": [c.model_dump() for c in chunks],
                    "latencies": {
                        "embed_ms": round(embed_ms, 2),
                        "retrieve_ms": round(retrieve_ms, 2),
                        "rerank_ms": round(rerank_ms, 2),
                        "llm_ms": round(llm_ms, 2),
                        "total_ms": round(total_ms, 2),
                    },
                }
                yield f"data: {json.dumps(done)}\n\n"

        except Exception as exc:
            logger.exception("SSE stream error")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Chat history

@app.get("/chat-history", tags=["chat"])
async def chat_history(
    limit: int = Query(default=50, ge=1, le=200),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """Return the authenticated user's persisted chat messages, newest first."""
    user_id = x_user_id or _user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    messages = await db.get_chat_history(user_id, limit)
    return {"messages": messages}


class InitSessionRequest(BaseModel):
    session_id: str
    disease: Optional[str] = None
    image_url: Optional[str] = None
    disease_display: Optional[str] = None


@app.post("/chat-session/init", tags=["chat"])
async def init_chat_session(
    req: InitSessionRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """Create an initial chat session record from a prediction result (no LLM call)."""
    user_id = x_user_id or _user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    name = req.disease_display or req.disease or "cây trồng"
    await db.save_chat_message(
        user_id=user_id,
        session_id=req.session_id,
        disease=req.disease,
        question=f"Phân tích ảnh: {name}",
        answer=f"Đã phát hiện: {name}. Hãy hỏi tôi về triệu chứng, nguyên nhân hoặc cách phòng trị.",
        image_url=req.image_url,
    )
    return {"ok": True}


@app.get("/chat-session/{session_id}", tags=["chat"])
async def chat_session_messages(
    session_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """Return all messages for a specific session (for resuming a chat)."""
    user_id = x_user_id or _user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    messages = await db.get_session_messages(user_id, session_id)
    return {"messages": messages}


@app.delete("/chat-session/{session_id}", tags=["chat"])
async def delete_chat_session(
    session_id: str,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """Delete all messages in a chat session."""
    user_id = x_user_id or _user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    deleted = await db.delete_session(user_id, session_id)
    return {"deleted": deleted}


# Feedback

@app.post("/feedback", response_model=FeedbackResponse, tags=["feedback"])
async def submit_feedback(
    req: FeedbackRequest,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """Record a user's verdict on a diagnosis.

    Confirms or corrects the predicted label, copies the verified image into the
    verified bucket (best-effort), persists to PostgreSQL, and publishes a Kafka
    event for downstream analytics / retraining.
    """
    user_id = x_user_id or _user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Decide the confirmed label and whether we have a reliable (gold) label.
    #   correct                → AI label is the gold label
    #   wrong + corrected       → user-provided label is the gold label
    #   wrong + no correction   → user doesn't know; leave for an expert to resolve.
    #                             Store a placeholder; do NOT feed the verified set.
    if req.is_correct:
        confirmed_label = req.predicted_disease
        has_gold_label = True
    elif req.corrected_disease:
        confirmed_label = req.corrected_disease
        has_gold_label = True
    else:
        confirmed_label = req.predicted_disease
        has_gold_label = False

    verified_path = (
        await feedback_minio.copy_to_verified(req.image_url, confirmed_label)
        if has_gold_label else None
    )

    feedback_id = await db.save_feedback(
        user_id=user_id,
        predicted_disease=req.predicted_disease,
        is_correct=req.is_correct,
        confirmed_label=confirmed_label,
        session_id=req.session_id,
        image_url=req.image_url,
        predicted_confidence=req.predicted_confidence,
        corrected_disease=req.corrected_disease,
        comment=req.comment,
        verified_image_path=verified_path,
    )
    if feedback_id is None:
        raise HTTPException(status_code=503, detail="Could not persist feedback")

    if _producer:
        try:
            await _producer.publish(
                topic=TOPIC_FEEDBACK_SUBMITTED,
                event_type="feedback.submitted",
                payload={
                    "feedback_id": feedback_id,
                    "user_id": user_id,
                    "predicted_disease": req.predicted_disease,
                    "is_correct": req.is_correct,
                    "corrected_disease": req.corrected_disease,
                    "confirmed_label": confirmed_label,
                    "verified_image_path": verified_path,
                },
            )
        except Exception:
            logger.warning("Failed to publish feedback.submitted event", exc_info=True)

    return FeedbackResponse(
        id=feedback_id,
        confirmed_label=confirmed_label,
        verified_image_path=verified_path,
    )


@app.get("/feedback", response_model=list[FeedbackItem], tags=["feedback"])
async def feedback_history(
    limit: int = Query(default=50, ge=1, le=200),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
):
    """Return the authenticated user's feedback records, newest first."""
    user_id = x_user_id or _user_id_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    rows = await db.get_feedback_history(user_id, limit)
    return [FeedbackItem(**r) for r in rows]


# Ingestion

@app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK, tags=["ingestion"])
def ingest_directory(body: IngestDirectoryRequest = IngestDirectoryRequest()):
    """Ingest all documents from a directory on the server."""
    try:
        result = rag_service.ingest_directory(
            directory=body.directory,
            recreate_collection=body.recreate_collection,
        )
        return IngestResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Ingestion failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/reindex", response_model=IngestResponse, status_code=status.HTTP_200_OK, tags=["ingestion"])
def reindex():
    """Drop collection and re-ingest from the default knowledge directory."""
    try:
        result = rag_service.ingest_directory(recreate_collection=True)
        return IngestResponse(**result)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Reindex failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest/upload", response_model=IngestResponse, tags=["ingestion"])
async def ingest_upload(file: UploadFile = File(...)):
    """Upload and ingest a single document file."""
    from rag.core.config import get_settings
    from rag.ingestion.loader import DocumentLoader

    settings = get_settings()
    if not file.filename:
        raise HTTPException(status_code=422, detail="Missing filename.")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported type '{suffix}'.")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File too large.")

    if app_state.rag_chain is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not ready.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        loader = DocumentLoader()
        doc = loader.load_file(tmp_path)
        if not doc:
            raise HTTPException(status_code=422, detail="Could not parse file.")
        doc.filename = file.filename
        doc.source = file.filename

        result = app_state.rag_chain.ingest_documents([doc])
        app_state.vectors_count = app_state.rag_chain.qdrant.count()
        return IngestResponse(
            chunks_created=result.chunks_created,
            documents_processed=result.documents_processed,
            collection=settings.qdrant_collection,
            elapsed_seconds=result.elapsed_seconds,
        )
    finally:
        tmp_path.unlink(missing_ok=True)


# Collection

@app.get("/collection", response_model=CollectionStatsResponse, tags=["collection"])
def collection_stats():
    settings = get_settings()
    return CollectionStatsResponse(
        collection=settings.qdrant_collection,
        vectors_count=app_state.vectors_count,
        status="ok" if app_state.vectordb_connected else "unreachable",
    )


@app.delete("/collection", status_code=200, tags=["collection"])
def delete_collection():
    """Permanently delete the Qdrant collection."""
    if app_state.rag_chain is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not ready.")
    try:
        app_state.rag_chain.qdrant.delete_collection()
        app_state.vectors_count = 0
        return {"message": "Collection deleted."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Admin

@app.post("/admin/rebuild-bm25", tags=["admin"])
async def rebuild_bm25():
    """Scroll all chunks from Qdrant and rebuild the on-disk BM25 index."""
    if app_state.rag_chain is None:
        raise HTTPException(status_code=503, detail="RAG pipeline not ready.")
    try:
        await asyncio.to_thread(app_state.rag_chain.rebuild_bm25_index)
        from rag.core.config import get_settings as _get_settings
        _s = _get_settings()
        return {
            "status": "rebuilt",
            "bm25_index_path": _s.bm25_index_path,
        }
    except Exception as exc:
        logger.exception("BM25 rebuild failed")
        raise HTTPException(status_code=500, detail=f"Rebuild failed: {exc}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
