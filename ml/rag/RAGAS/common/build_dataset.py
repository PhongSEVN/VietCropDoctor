"""Dựng dataset cho RAGAS bằng cách chạy CHÍNH pipeline RAG thật.

Với mỗi câu hỏi → pipeline.query() → lấy (câu trả lời của LLM, các chunk đã đưa
vào LLM). Đây đúng là thứ RAGAS cần để chấm:
  - retrieved_contexts = các chunk retriever trả về (sau rerank) — LLM đã "thấy".
  - response           = câu trả lời LLM sinh ra.
  - reference (tùy)    = đáp án mẫu (chỉ RAGAS full cần, cho context_recall…).

Cần Qdrant đang chạy + Ollama đang chạy (LLM sinh câu trả lời).
"""
from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import Optional

from common.paths import ensure_rag_importable


def load_questions(path: Path | str) -> list[dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


async def _build(questions: list[dict[str, str]], qdrant_host: Optional[str],
                 llm_model: Optional[str]) -> list[dict]:
    ensure_rag_importable()
    from rag.core.config import get_settings
    from rag.pipeline import RAGPipeline

    s = get_settings()
    if qdrant_host:
        s.qdrant_host = qdrant_host
    if llm_model:
        s.llm_model = llm_model

    pipeline = RAGPipeline(s)
    pipeline.initialize()
    try:
        pipeline.rebuild_bm25_index()  # dùng hybrid như production; bỏ qua nếu lỗi
    except Exception:
        pass

    samples: list[dict] = []
    for item in questions:
        q = item["question"].strip()
        resp = await pipeline.query(question=q)
        row = {
            "user_input": q,
            "response": resp.answer,
            "retrieved_contexts": [c.text for c in resp.chunks],
        }
        ref = (item.get("reference") or "").strip()
        if ref:
            row["reference"] = ref
        samples.append(row)
        print(f"  ✓ {q[:48]}… ({len(resp.chunks)} contexts)", flush=True)

    pipeline.shutdown()
    return samples


def build_dataset(questions: list[dict[str, str]], qdrant_host: Optional[str] = None,
                  llm_model: Optional[str] = None) -> list[dict]:
    """Chạy pipeline RAG cho mọi câu hỏi, trả list bản ghi cho RAGAS."""
    return asyncio.run(_build(questions, qdrant_host, llm_model))


def save_jsonl(samples: list[dict], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def load_jsonl(path: Path | str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
