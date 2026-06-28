"""
Orchestrator microservice — FastAPI entry point.

Endpoints:
  POST /orchestrate    — full multi-agent pipeline (image → vision → rag → recommendation)
  GET  /health         — readiness check with downstream service reachability
  GET  /docs           — Swagger UI
"""
from __future__ import annotations

import base64
import logging
import os
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from vcd_shared.auth import get_current_user
from vcd_shared.logging import setup_logging

from app.config import get_settings
from app.reasoning.chain import OrchestrationChain
from app.reasoning.llm_router import LLMRouter
from app.schemas import OrchestrationHealthResponse, OrchestrationResponse

logger = logging.getLogger("orchestrator.main")

_chain: OrchestrationChain | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _chain
    cfg = get_settings()
    setup_logging(level=cfg.log_level)
    logger.info("=" * 55)
    logger.info("Starting VietCropDoctor Orchestrator")
    logger.info("=" * 55)
    _chain = OrchestrationChain()
    logger.info("Orchestrator ready.")
    yield
    logger.info("Orchestrator shutting down.")


cfg = get_settings()

app = FastAPI(
    title="VietCropDoctor Orchestrator",
    version="1.0.0",
    description="Multi-agent AI pipeline: vision → retrieval → reasoning → recommendation",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.post("/orchestrate", response_model=OrchestrationResponse, tags=["orchestration"])
async def orchestrate(
    image: UploadFile = File(..., description="Crop image to analyse"),
    query: str | None = Form(default=None, description="Optional follow-up question"),
    session_id: str | None = Query(default=None),
    x_user_id: str = Header(default="", alias="X-User-Id"),
):
    if _chain is None:
        raise HTTPException(status_code=503, detail="Service initialising")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB")

    context = {
        "image_base64": base64.b64encode(image_bytes).decode(),
        "query": query,
        "session_id": session_id or str(uuid.uuid4()),
        "user_id": x_user_id or None,
    }

    try:
        result = await _chain.run(context)
    except Exception as exc:
        logger.exception("Orchestration failed")
        raise HTTPException(status_code=502, detail=f"Pipeline error: {exc}")

    return result


@app.get("/health", response_model=OrchestrationHealthResponse, tags=["system"])
async def health():
    cfg = get_settings()
    llm_ok = rag_ok = vision_ok = False

    async with httpx.AsyncClient(timeout=3) as client:
        try:
            r = await client.get(f"{cfg.vision_ai_url}/health")
            vision_ok = r.status_code == 200
        except Exception:
            pass
        try:
            r = await client.get(f"{cfg.rag_engine_url}/health")
            rag_ok = r.status_code == 200
        except Exception:
            pass

    llm_ok = await LLMRouter().is_reachable()

    status = "ok" if all([vision_ok, rag_ok]) else "degraded"
    return OrchestrationHealthResponse(
        status=status,
        vision_ai_reachable=vision_ok,
        rag_engine_reachable=rag_ok,
        ollama_reachable=llm_ok,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8006, reload=True)
