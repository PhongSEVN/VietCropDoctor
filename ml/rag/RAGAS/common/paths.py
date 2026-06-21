"""Đảm bảo package `rag` của rag-engine import được khi chạy ngoài service.

Trong container rag-engine thì `rag` đã có sẵn trên sys.path. Trên host thì chèn
thư mục backend/services/ai/rag-engine vào sys.path để dùng CHUNG đúng pipeline
(embedder, retriever, reranker, LLM) — tránh lệch so với hệ thống thật.
"""
from __future__ import annotations

import sys
from pathlib import Path


def ensure_rag_importable() -> None:
    """Chèn rag-engine vào sys.path nếu `rag` chưa import được. Idempotent."""
    try:
        import rag  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "backend" / "services" / "ai" / "rag-engine"
        if (candidate / "rag").is_dir():
            sys.path.insert(0, str(candidate))
            return

    for guess in ("/app", "/app/rag-engine"):
        if (Path(guess) / "rag").is_dir():
            sys.path.insert(0, guess)
            return

    raise ModuleNotFoundError(
        "Không tìm thấy package `rag`. Chạy trong container rag-engine, hoặc đảm bảo "
        "thư mục backend/services/ai/rag-engine có trong cây dự án."
    )
