"""
Prometheus custom metrics for the RAG Engine service.

Imported by main.py and recorded in the /query endpoint.
"""
from prometheus_client import Counter, Histogram

rag_queries_total = Counter(
    "rag_queries_total",
    "Total RAG queries processed",
    ["crop"],
)

rag_latency = Histogram(
    "rag_latency_seconds",
    "RAG pipeline latency broken down by stage (embed|retrieve|rerank|llm)",
    ["stage"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

chunks_retrieved = Histogram(
    "chunks_retrieved",
    "Number of chunks returned per query after reranking",
    buckets=[1, 2, 3, 5, 8],
)
