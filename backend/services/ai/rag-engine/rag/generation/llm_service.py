"""
LLM service abstraction.

Currently supports Ollama (primary). The abstract base class makes it easy
to swap in a transformers local-inference backend later.

Ollama integration features:
  - Async HTTP via httpx
  - Streaming via Server-Sent Events (SSE)
  - Exponential-backoff retry on transient errors
  - Configurable timeout, temperature, max_tokens
"""
from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional

import httpx

from rag.core.exceptions import LLMError, LLMUnavailableError
from rag.generation.prompt_builder import build_system_prompt, build_user_message
from rag.models.responses import RetrievedChunk

logger = logging.getLogger(__name__)


# Abstract base

class BaseLLMService(ABC):
    """Contract for all LLM backends."""

    @abstractmethod
    async def generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        history: Optional[list[dict[str, str]]] = None,
    ) -> str:
        """Return a complete answer string."""

    @abstractmethod
    async def stream_generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        history: Optional[list[dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield answer tokens as they are generated."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the LLM backend is reachable."""


# Ollama implementation

class OllamaLLMService(BaseLLMService):
    """LLM service backed by a local Ollama server.

    Args:
        model:       Ollama model tag (e.g. "qwen2.5:7b").
        base_url:    Ollama HTTP base URL.
        temperature: Sampling temperature.
        max_tokens:  Maximum tokens to generate.
        timeout:     HTTP request timeout in seconds.
        max_retries: Retries on connection error (exponential backoff).
    """

    _GENERATE_PATH = "/api/generate"
    _TAGS_PATH = "/api/tags"

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

        logger.info(
            "OllamaLLMService configured | model=%s url=%s temp=%.2f",
            model, base_url, temperature,
        )

    # Public API

    async def generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        history: Optional[list[dict[str, str]]] = None,
    ) -> str:
        """Non-streaming generation with retry."""
        prompt = self._build_prompt(question, chunks, history)
        payload = self._build_payload(prompt, stream=False)

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self.base_url + self._GENERATE_PATH,
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    answer = data.get("response", "").strip()
                    logger.debug(
                        "LLM generated %d chars | model=%s",
                        len(answer), self.model,
                    )
                    return answer

            except httpx.ConnectError as exc:
                if attempt == self.max_retries:
                    raise LLMUnavailableError(
                        f"Ollama is not reachable at {self.base_url}. "
                        "Make sure `ollama serve` is running."
                    ) from exc
                wait = 2 ** attempt
                logger.warning("Ollama connection failed (attempt %d), retrying in %ds…", attempt + 1, wait)
                await asyncio.sleep(wait)

            except httpx.TimeoutException as exc:
                raise LLMError(
                    f"Ollama request timed out after {self.timeout}s.",
                    details={"model": self.model},
                ) from exc

            except Exception as exc:
                raise LLMError(f"LLM generation error: {exc}") from exc

        return ""  # unreachable

    async def stream_generate(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        history: Optional[list[dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield tokens as they stream from Ollama."""
        prompt = self._build_prompt(question, chunks, history)
        payload = self._build_payload(prompt, stream=True)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    self.base_url + self._GENERATE_PATH,
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk_data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        token = chunk_data.get("response", "")
                        if token:
                            yield token
                        if chunk_data.get("done"):
                            break

        except httpx.ConnectError as exc:
            raise LLMUnavailableError(
                f"Ollama is not reachable at {self.base_url}."
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama stream timed out after {self.timeout}s.") from exc
        except Exception as exc:
            raise LLMError(f"LLM stream error: {exc}") from exc

    async def health_check(self) -> bool:
        """Return True if Ollama responds and the target model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.base_url + self._TAGS_PATH)
                if resp.status_code != 200:
                    return False
                models = [m["name"] for m in resp.json().get("models", [])]
                available = any(self.model in m for m in models)
                if not available:
                    logger.warning(
                        "Model '%s' not found in Ollama. Available: %s",
                        self.model, models,
                    )
                return True          # server reachable even if model not pulled
        except Exception:
            return False

    # Private

    def _build_prompt(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        history: Optional[list[dict[str, str]]],
    ) -> str:
        """Combine system prompt + user message into a single string for Ollama."""
        system = build_system_prompt()
        user = build_user_message(question, chunks, history)
        return f"{system}\n\n{user}"

    def _build_payload(self, prompt: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
                "stop": ["[CÂU HỎI]", "Người dùng:"],
            },
        }
