"""Đảm bảo package `rag` của rag-engine import được khi chạy ngoài service.

Trong container rag-engine, `rag` đã nằm sẵn trên sys.path nên không cần làm gì.
Khi chạy trên host, ta chèn thư mục backend/services/ai/rag-engine vào sys.path
(giống cơ chế của ml/rag/_bootstrap.py) để dùng CHUNG đúng embedder + prefix
"query:"/"passage:" với lúc index — tránh lệch model gây hỏng retrieval ngầm.
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

    # Bố cục container phổ biến (app copy thẳng rag-engine vào /app)
    for guess in ("/app", "/app/rag-engine"):
        if (Path(guess) / "rag").is_dir():
            sys.path.insert(0, guess)
            return

    raise ModuleNotFoundError(
        "Không tìm thấy package `rag`. Hãy chạy trong container rag-engine, "
        "hoặc đảm bảo thư mục backend/services/ai/rag-engine có trong cây dự án."
    )
