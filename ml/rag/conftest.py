"""Pytest bootstrap for ml/rag offline tests.

Adds the rag-engine service directory to sys.path so the tests can import the
shared ``rag`` package (the same library the online service uses). Kept
self-contained so it works regardless of pytest's import mode / rootdir.
"""
import sys
from pathlib import Path

# ml/rag/conftest.py → ml/rag → ml → repo root
_RAG_ENGINE = Path(__file__).resolve().parents[2] / "backend" / "services" / "ai" / "rag-engine"
if str(_RAG_ENGINE) not in sys.path:
    sys.path.insert(0, str(_RAG_ENGINE))
