"""
RetrievalAgent — formulates a RAG query from the vision result
and calls rag-engine /query to retrieve treatment knowledge.

Reads `vision_result` from context.
Writes `retrieval_result` (RetrievalResult) back.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.agents.base_agent import BaseAgent
from app.config import get_settings
from app.schemas import RetrievalResult

logger = logging.getLogger("orchestrator.retrieval_agent")


def _build_rag_query(disease: str, severity: str, user_query: str | None) -> str:
    base = f"Bệnh {disease} trên cây trồng, mức độ {severity}. Cách điều trị và phòng ngừa?"
    if user_query:
        return f"{user_query}\n\nContext: {base}"
    return base


class RetrievalAgent(BaseAgent):
    name = "retrieval"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        cfg = get_settings()
        vision: Any = context["vision_result"]

        query = _build_rag_query(
            disease=vision.disease,
            severity=vision.severity,
            user_query=context.get("query"),
        )

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{cfg.rag_engine_url}/query",
                    json={
                        "question": query,
                        "disease_filter": vision.disease,
                        "top_k": 5,
                        "stream": False,
                        # Fetch context chunks only — the Orchestrator runs the
                        # single reasoning LLM call itself, so RAG must NOT also
                        # generate an answer (avoids a redundant LLM invocation).
                        "retrieve_only": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("RAG engine call failed: %s — skipping retrieval", exc)
            context["retrieval_result"] = None
            return context

        elapsed = (time.perf_counter() - t0) * 1000
        context.setdefault("latency_ms", {})["retrieval_ms"] = round(elapsed, 1)

        chunks = data.get("chunks", [])
        sources = [c["source"] for c in chunks]
        # Build the knowledge text the reasoning LLM consumes by concatenating the
        # retrieved chunk texts (RAG no longer returns a generated answer here).
        knowledge_text = "\n\n".join(
            c.get("text", "").strip() for c in chunks if c.get("text", "").strip()
        )
        context["retrieval_result"] = RetrievalResult(
            answer=knowledge_text,
            sources=list(dict.fromkeys(sources)),   # deduplicate preserving order
            chunks_used=len(chunks),
        )
        logger.info(
            "RetrievalAgent: chunks_used=%d", context["retrieval_result"].chunks_used
        )
        return context
