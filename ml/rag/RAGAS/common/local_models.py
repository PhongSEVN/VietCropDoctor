"""Cấu hình RAGAS dùng MODEL LOCAL — Qwen (Ollama) làm LLM-judge + e5 embeddings.

Bắt buộc dùng local vì dự án không gọi cloud API (xem CLAUDE.md). Thông số đọc từ
Settings của rag-engine (llm_model, llm_base_url, embedding_model) nên khớp với
chính hệ thống đang chạy.
"""
from __future__ import annotations

from typing import Optional

from common.paths import ensure_rag_importable


def get_ragas_llm(model: Optional[str] = None, base_url: Optional[str] = None,
                  temperature: float = 0.0):
    """LLM-judge cho RAGAS = Qwen qua Ollama, bọc trong LangchainLLMWrapper."""
    ensure_rag_importable()
    from rag.core.config import get_settings
    try:
        from langchain_ollama import ChatOllama
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Thiếu `langchain-ollama`. Cài: pip install langchain-ollama"
        ) from exc
    from ragas.llms import LangchainLLMWrapper

    s = get_settings()
    chat = ChatOllama(
        model=model or s.llm_model,
        base_url=base_url or s.llm_base_url,
        temperature=temperature,  # judge nên xác định (0.0) cho ổn định
    )
    return LangchainLLMWrapper(chat)


def get_ragas_embeddings(model: Optional[str] = None):
    """Embeddings cho RAGAS = multilingual-e5 (HuggingFace), chạy local."""
    ensure_rag_importable()
    from rag.core.config import get_settings
    try:
        from langchain_huggingface import HuggingFaceEmbeddings
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Thiếu `langchain-huggingface`. Cài: pip install langchain-huggingface"
        ) from exc
    from ragas.embeddings import LangchainEmbeddingsWrapper

    s = get_settings()
    emb = HuggingFaceEmbeddings(model_name=model or s.embedding_model)
    return LangchainEmbeddingsWrapper(emb)
