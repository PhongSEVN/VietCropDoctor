"""
Centralised logging configuration.

Call setup_logging() once at application startup. All modules then use
the standard `logging.getLogger(__name__)` pattern.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(level: str = "INFO", log_file: Optional[Path] = None) -> None:
    """Configure root logger with console (and optional file) handlers.

    Args:
        level:    Log level string (DEBUG / INFO / WARNING / ERROR).
        log_file: If provided, also write logs to this file.
    """
    fmt = "%(asctime)s | %(levelname)-8s | %(name)-35s | %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [
        _make_stream_handler(fmt, datefmt),
    ]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(_make_file_handler(log_file, fmt, datefmt))

    logging.basicConfig(
        level=numeric_level,
        handlers=handlers,
        force=True,  # override any handlers set by imported libs
    )

    _silence_noisy_loggers()
    logging.getLogger(__name__).debug("Logging initialised at level=%s", level)


def _make_stream_handler(fmt: str, datefmt: str) -> logging.StreamHandler:
    # On Windows, the default console encoding (cp1252) cannot represent
    # non-ASCII characters. Wrap stdout with UTF-8 when buffer is available.
    import io
    stream = sys.stdout
    try:
        if hasattr(sys.stdout, "buffer"):
            stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace", line_buffering=True)
    except Exception:
        pass  # fall back to default stdout if wrapping fails
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    return handler


def _make_file_handler(
    path: Path, fmt: str, datefmt: str
) -> logging.FileHandler:
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
    return handler


def _silence_noisy_loggers() -> None:
    """Reduce verbosity of third-party libraries."""
    for name in (
        "httpx",
        "httpcore",
        "urllib3",
        "sentence_transformers",
        "transformers",
        "torch",
        "qdrant_client",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
