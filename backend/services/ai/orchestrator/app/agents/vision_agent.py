"""
VisionAgent — wraps the vision-ai /predict endpoint.

Reads `image_base64` from the context.
Writes `vision_result` (VisionResult) back into the context.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from app.agents.base_agent import BaseAgent
from app.config import get_settings
from app.schemas import VisionResult

logger = logging.getLogger("orchestrator.vision_agent")


class VisionAgent(BaseAgent):
    name = "vision"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        cfg = get_settings()
        image_bytes = base64.b64decode(context["image_base64"])

        # Forward the authenticated user id so vision-ai attributes the
        # disease.detected Kafka event to the correct user.
        headers = {}
        user_id = context.get("user_id")
        if user_id:
            headers["X-User-Id"] = str(user_id)

        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{cfg.vision_ai_url}/predict",
                    files={"image": ("image.jpg", image_bytes, "image/jpeg")},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("Vision-AI call failed: %s", exc)
            raise

        elapsed = (time.perf_counter() - t0) * 1000
        context.setdefault("latency_ms", {})["vision_ms"] = round(elapsed, 1)

        context["vision_result"] = VisionResult(
            disease=data["disease"],
            confidence=data["confidence"],
            severity=data.get("severity", "mild"),
            severity_score=data.get("severity_score", 0.0),
            severity_advice=data.get("severity_advice", ""),
            top3=data.get("top3", []),
            uncertainty_score=data.get("uncertainty_score"),
            ensemble_used=data.get("ensemble_used", False),
            explanation=data.get("explanation", ""),
            agreement_score=data.get("agreement_score", 1.0),
            model_count=data.get("model_count", 1),
            image_url=data.get("image_url"),
            is_in_distribution=data.get("is_in_distribution", True),
            ood_message=data.get("ood_message"),
            ood_score=data.get("ood_score"),
        )
        logger.info(
            "VisionAgent: disease=%s confidence=%.3f severity=%s",
            data["disease"], data["confidence"], data.get("severity"),
        )
        return context
