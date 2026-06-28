"""
Reindex script — Phase 1 one-time knowledge base indexing (chạy tay).

Drop collection Qdrant cũ và ingest lại TOÀN BỘ tài liệu trong thư mục
knowledge, dùng ĐÚNG pipeline mà endpoint /reindex của API đang dùng
(loader → cleaner → chunker → embedder → Qdrant + rebuild BM25).

Cách chạy (bên trong container rag-engine đang chạy):
    docker exec -it vcd-rag-engine python reindex.py

Đây KHÔNG phải build_vectordb.py (file cũ, dùng OpenAI embedder — đã lỗi thời,
KHÔNG tương thích với pipeline local hiện tại). Dùng file này.
"""
import logging
import os
import sys
from pathlib import Path

# Tự cấu hình khi chạy NGOÀI Docker (trên host)
# Bên trong container có /.dockerenv; khi chạy host thì không.
# Trên host: hostname "qdrant"/"ollama" của mạng Docker không phân giải được,
# nên trỏ về localhost (Qdrant đã expose cổng 6333). Đồng thời chuyển cwd về
# thư mục script để các đường dẫn tương đối (rag/knowledge, data/bm25_index.pkl)
# phân giải đúng và KHÔNG nạp nhầm .env của Docker (QDRANT_HOST=qdrant).
# PHẢI đặt TRƯỚC khi import config/rag_service vì get_settings() cache env ngay.
_IN_DOCKER = Path("/.dockerenv").exists()
if not _IN_DOCKER:
    os.chdir(Path(__file__).resolve().parent)
    os.environ["QDRANT_HOST"] = "localhost"
    os.environ.setdefault("LLM_BASE_URL", "http://localhost:11434")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")

from app.rag_service import ingest_directory, load_rag_chain
from app.state import app_state
from rag.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("reindex")


def main() -> int:
    settings = get_settings()
    log.info("=" * 60)
    log.info("REINDEX — Phase 1 (one-time)")
    log.info("  Knowledge dir : %s", settings.knowledge_dir)
    log.info("  Collection    : %s", settings.qdrant_collection)
    log.info("  Embedding     : %s (%d-dim)",
             settings.embedding_model, settings.embedding_vector_size)
    log.info("  Qdrant        : %s:%s", settings.qdrant_host, settings.qdrant_port)
    log.info("  Reranker      : %s", settings.reranker_model)
    log.info("=" * 60)

    # Khởi tạo pipeline: tải model embedding + kết nối Qdrant.
    # Lần đầu sẽ tải model embedding nếu hf_cache trống.
    log.info("Đang khởi tạo RAG pipeline (load model + connect Qdrant)...")
    load_rag_chain()
    if app_state.rag_chain is None:
        log.error("Khởi tạo pipeline THẤT BẠI — xem log phía trên. Dừng.")
        return 1

    # Drop collection cũ + ingest lại từ đầu + rebuild BM25.
    log.info("Bắt đầu REINDEX — xoá collection cũ và ingest lại toàn bộ...")
    stats = ingest_directory(recreate_collection=True)

    log.info("=" * 60)
    log.info("REINDEX HOÀN TẤT")
    log.info("  documents_processed = %s", stats["documents_processed"])
    log.info("  chunks_created      = %s", stats["chunks_created"])
    log.info("  collection          = %s", stats["collection"])
    log.info("  elapsed_seconds     = %.1f", stats["elapsed_seconds"])
    log.info("  vectors trong Qdrant = %s", app_state.vectors_count)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
