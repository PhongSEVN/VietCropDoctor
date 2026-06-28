"""
LLM router — sends prompts to Ollama and streams/collects the response.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.reasoning.prompts import SYSTEM_PROMPT

logger = logging.getLogger("orchestrator.llm_router")


class LLMRouter:
    """Thin async wrapper around the Ollama /api/chat endpoint."""

    async def generate(self, user_prompt: str) -> str:
        cfg = get_settings()
        payload = {
            "model": cfg.reasoning_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": cfg.reasoning_temperature,
                "num_predict": 1024,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=cfg.reasoning_timeout_seconds) as client:
                resp = await client.post(
                    f"{cfg.ollama_base_url}/api/chat",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
        except Exception as exc:
            logger.error("LLM generation failed: %s", exc)
            return ""

    async def is_reachable(self) -> bool:
        cfg = get_settings()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{cfg.ollama_base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
