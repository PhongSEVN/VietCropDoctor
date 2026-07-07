"""
RecommendationAgent — synthesizes vision + retrieval results into
structured, actionable treatment recommendations using the reasoning LLM.

Reads `vision_result`, `retrieval_result`, `reasoning_output` from context.
Writes `recommendation` (Recommendation) back.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.schemas import Recommendation

logger = logging.getLogger("orchestrator.recommendation_agent")

# Urgency mapping based on severity
_URGENCY_MAP = {
    "healthy": "low",
    "mild":    "low",
    "moderate": "medium",
    "severe":   "high",
    "high":     "high",
    "critical": "critical",
}


def _extract_list(text: str, marker: str) -> list[str]:
    """Extract bullet points following a section marker.

    The reasoning prompt asks the LLM for markdown-bold markers
    (`**Hành động ngay**:`), so the marker itself may be wrapped in `**` —
    match that optionally rather than requiring the bare marker text.
    """
    pattern = rf"\*{{0,2}}\s*{re.escape(marker)}\s*\*{{0,2}}[:\s]*\n((?:[-•*]\s*.+\n?)+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return []
    items = re.findall(r"[-•*]\s*(.+)", match.group(1))
    return [i.strip() for i in items if i.strip()]


class RecommendationAgent(BaseAgent):
    name = "recommendation"

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        vision = context["vision_result"]
        reasoning_output: str = context.get("reasoning_output", "")

        urgency = _URGENCY_MAP.get(vision.severity, "medium")
        if vision.confidence < 0.5:
            urgency = "low"   # low confidence → don't alarm

        immediate = _extract_list(reasoning_output, "Hành động ngay")
        preventive = _extract_list(reasoning_output, "Phòng ngừa")
        treatment  = _extract_list(reasoning_output, "Điều trị")
        monitoring = ""
        m = re.search(r"\*{0,2}\s*Theo dõi\s*\*{0,2}[:\s]*(.+?)(?:\n|$)", reasoning_output, re.IGNORECASE)
        if m:
            monitoring = m.group(1).strip()

        # Fallback defaults when LLM produced no structured output
        if not immediate:
            immediate = [
                f"Cách ly cây bị nhiễm {vision.disease} để tránh lây lan",
                "Kiểm tra các cây lân cận",
            ]
        if not treatment:
            treatment = [f"Tham khảo chuyên gia về phương pháp điều trị {vision.disease}"]
        if not preventive:
            preventive = ["Duy trì vệ sinh vườn, đảm bảo thông thoáng"]
        if not monitoring:
            monitoring = f"Theo dõi triệu chứng {vision.disease} hàng ngày trong 2 tuần tới"

        context["recommendation"] = Recommendation(
            immediate_actions=immediate,
            preventive_measures=preventive,
            treatment_options=treatment,
            monitoring_advice=monitoring,
            urgency=urgency,
        )
        logger.info("RecommendationAgent: urgency=%s", urgency)
        return context
