"""
Multi-step reasoning chain:
  VisionAgent → RetrievalAgent → LLM Reasoning → RecommendationAgent
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.vision_agent import VisionAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.recommend_agent import RecommendationAgent
from app.reasoning.llm_router import LLMRouter
from app.reasoning.prompts import build_reasoning_prompt
from app.schemas import OrchestrationResponse

logger = logging.getLogger("orchestrator.chain")


class OrchestrationChain:
    """Executes the full agent pipeline and returns a typed response."""

    def __init__(self) -> None:
        self._vision = VisionAgent()
        self._retrieval = RetrievalAgent()
        self._recommendation = RecommendationAgent()
        self._llm = LLMRouter()

    async def run(self, context: dict[str, Any]) -> OrchestrationResponse:
        t_total = time.perf_counter()
        context.setdefault("latency_ms", {})

        # Step 1: Vision
        context = await self._vision.execute(context)
        vision = context["vision_result"]

        # Early stop: out-of-distribution image (not a crop leaf). Skip
        # retrieval, reasoning, and recommendation — there is no disease to
        # treat. Return the vision result with the OOD guidance message.
        if not vision.is_in_distribution:
            context["latency_ms"]["total_ms"] = round((time.perf_counter() - t_total) * 1000, 1)
            logger.info("OrchestrationChain: OOD image — early stop")
            return OrchestrationResponse(
                session_id=context.get("session_id"),
                vision=vision,
                knowledge=None,
                recommendation=None,
                reasoning_summary=vision.ood_message or "Ảnh không hợp lệ.",
                latency_ms=context["latency_ms"],
            )

        # Step 2: Retrieval
        context = await self._retrieval.execute(context)
        retrieval = context.get("retrieval_result")

        # Step 3: LLM reasoning
        t0 = time.perf_counter()
        prompt = build_reasoning_prompt(
            disease=vision.disease,
            confidence=vision.confidence,
            severity=vision.severity,
            severity_score=vision.severity_score,
            severity_advice=vision.severity_advice,
            knowledge_text=retrieval.answer if retrieval else "",
            user_query=context.get("query"),
        )
        reasoning_output = await self._llm.generate(prompt)
        context["reasoning_output"] = reasoning_output
        context["latency_ms"]["llm_ms"] = round((time.perf_counter() - t0) * 1000, 1)

        # Step 4: Recommendation
        context = await self._recommendation.execute(context)

        context["latency_ms"]["total_ms"] = round((time.perf_counter() - t_total) * 1000, 1)

        # Extract summary (first paragraph of reasoning output)
        summary_lines = [
            line.strip() for line in reasoning_output.split("\n")
            if line.strip() and not line.startswith("**")
        ]
        reasoning_summary = summary_lines[0] if summary_lines else f"Đã phát hiện {vision.disease}."

        return OrchestrationResponse(
            session_id=context.get("session_id"),
            vision=vision,
            knowledge=retrieval,
            recommendation=context["recommendation"],
            reasoning_summary=reasoning_summary,
            latency_ms=context["latency_ms"],
        )
