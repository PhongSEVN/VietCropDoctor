"""
Global RAG service state — loaded once at startup via lifespan.
Access via `from app.state import app_state`.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class AppState:
    rag_chain: Any = None          # RAGPipeline instance
    vectordb_connected: bool = False
    vectors_count: int = 0


app_state = AppState()
