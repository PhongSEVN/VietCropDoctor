"""Path bootstrap for offline RAG tools.

The shared RAG library (embedder, retriever, qdrant client, ingestion, pipeline)
lives in the ONLINE service at ``backend/services/ai/rag-engine/``. Offline tools
in ``ml/rag/`` import that same ``rag`` package instead of duplicating the
embedding / indexing logic — this guarantees the embedding model and the
``query:`` / ``passage:`` prefixes stay identical between index time and query
time (a mismatch would silently break retrieval).

Import this module BEFORE importing anything from ``rag.*``::

    import _bootstrap  # noqa: F401
    from rag.pipeline import RAGPipeline

Note: running these tools still requires the rag-engine dependencies
(sentence-transformers, qdrant-client, torch, …) to be installed in the
current environment, or run them inside the rag-engine container.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ml/rag/_bootstrap.py → ml/rag → ml → repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RAG_ENGINE = _REPO_ROOT / "backend" / "services" / "ai" / "rag-engine"

if not _RAG_ENGINE.exists():  # pragma: no cover - defensive
    raise RuntimeError(
        f"Cannot locate rag-engine package at '{_RAG_ENGINE}'. "
        "The offline RAG tools import the shared `rag` library from there."
    )

if str(_RAG_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RAG_ENGINE))
