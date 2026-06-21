"""
Offline indexing script.

Reads all documents from the knowledge directory, chunks them, embeds them,
and upserts into Qdrant.  Run this once before starting the API server, or
whenever knowledge files change.

Usage:
    python scripts/build_index.py [--dir rag/knowledge] [--recreate]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Make the shared `rag` package (in the rag-engine service) importable.
import _bootstrap  # noqa: F401,E402  (path shim — must run before importing rag)

from rag.core.config import get_settings
from rag.core.logging_config import setup_logging
from rag.pipeline import RAGPipeline

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Qdrant vector index")
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Knowledge directory (default: from settings)",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection before indexing",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(level=args.log_level)

    settings = get_settings()
    knowledge_dir = args.dir or settings.knowledge_dir

    logger.info("=" * 50)
    logger.info("Build Index Script")
    logger.info("Knowledge dir : %s", knowledge_dir)
    logger.info("Collection    : %s", settings.qdrant_collection)
    logger.info("Embedding     : %s", settings.embedding_model)
    logger.info("Recreate      : %s", args.recreate)
    logger.info("=" * 50)

    pipeline = RAGPipeline(settings)
    pipeline.initialize()

    start = time.perf_counter()
    result = pipeline.ingest_directory(knowledge_dir, recreate_collection=args.recreate)
    elapsed = time.perf_counter() - start

    logger.info("=" * 50)
    logger.info("Indexing complete!")
    logger.info("  Documents processed : %d", result.documents_processed)
    logger.info("  Chunks created      : %d", result.chunks_created)
    logger.info("  Total elapsed       : %.1f s", elapsed)
    logger.info("=" * 50)

    pipeline.shutdown()


if __name__ == "__main__":
    main()
