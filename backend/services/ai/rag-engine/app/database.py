"""
PostgreSQL connection pool for the RAG Engine.

Shares the same vcd_auth database as the auth service.
Used only for persisting chat messages — read/write is low-frequency.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger("rag_engine.database")

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> None:
    global _pool
    dsn = os.getenv("POSTGRES_DSN", "postgresql://vcdauth:secret@postgres:5432/vcd_auth")
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, command_timeout=10)
    logger.info("PostgreSQL pool initialized")
    # NOTE: The schema (users, chat_messages, feedback) is owned and migrated by
    # the auth service — see backend/services/core/auth/app/database.py:run_migrations.
    # The RAG engine only reads/writes these tables; it does not create them, so the
    # `feedback.user_id → users(id)` foreign key always resolves in the right order.


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def _get_pool() -> Optional[asyncpg.Pool]:
    return _pool


async def save_chat_message(
    user_id: str,
    session_id: str,
    disease: Optional[str],
    question: str,
    answer: str,
    image_url: Optional[str] = None,
) -> None:
    pool = await _get_pool()
    if pool is None:
        return
    try:
        await pool.execute(
            """
            INSERT INTO chat_messages (user_id, session_id, disease, question, answer, image_url)
            VALUES ($1::uuid, $2, $3, $4, $5, $6)
            """,
            user_id, session_id, disease, question, answer, image_url,
        )
    except Exception:
        logger.warning("Failed to save chat message", exc_info=True)


async def delete_session(user_id: str, session_id: str) -> int:
    pool = await _get_pool()
    if pool is None:
        return 0
    try:
        result = await pool.execute(
            "DELETE FROM chat_messages WHERE user_id = $1::uuid AND session_id = $2",
            user_id, session_id,
        )
        return int(result.split()[-1])
    except Exception:
        logger.warning("Failed to delete session", exc_info=True)
        return 0


async def get_session_messages(user_id: str, session_id: str) -> list[dict]:
    pool = await _get_pool()
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """
            SELECT id, session_id, disease, question, answer, image_url, created_at
            FROM chat_messages
            WHERE user_id = $1::uuid AND session_id = $2
            ORDER BY created_at ASC
            """,
            user_id, session_id,
        )
        return [
            {
                "id": str(r["id"]),
                "session_id": r["session_id"],
                "disease": r["disease"],
                "question": r["question"],
                "answer": r["answer"],
                "image_url": r["image_url"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("Failed to fetch session messages", exc_info=True)
        return []


async def get_chat_history(user_id: str, limit: int = 50) -> list[dict]:
    pool = await _get_pool()
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """
            SELECT id, session_id, disease, question, answer, image_url, created_at
            FROM chat_messages
            WHERE user_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id, limit,
        )
        return [
            {
                "id": str(r["id"]),
                "session_id": r["session_id"],
                "disease": r["disease"],
                "question": r["question"],
                "answer": r["answer"],
                "image_url": r["image_url"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("Failed to fetch chat history", exc_info=True)
        return []


async def save_feedback(
    user_id: str,
    predicted_disease: str,
    is_correct: bool,
    confirmed_label: str,
    *,
    session_id: Optional[str] = None,
    image_url: Optional[str] = None,
    predicted_confidence: float = 0.0,
    corrected_disease: Optional[str] = None,
    comment: Optional[str] = None,
    verified_image_path: Optional[str] = None,
) -> Optional[str]:
    """Persist a feedback record. Returns the new row id, or None on failure."""
    pool = await _get_pool()
    if pool is None:
        return None
    try:
        row = await pool.fetchrow(
            """
            INSERT INTO feedback (
                user_id, session_id, image_url, predicted_disease,
                predicted_confidence, is_correct, corrected_disease,
                confirmed_label, comment, verified_image_path
            )
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
            """,
            user_id, session_id, image_url, predicted_disease,
            predicted_confidence, is_correct, corrected_disease,
            confirmed_label, comment, verified_image_path,
        )
        return str(row["id"]) if row else None
    except Exception:
        logger.warning("Failed to save feedback", exc_info=True)
        return None


async def get_feedback_history(user_id: str, limit: int = 50) -> list[dict]:
    pool = await _get_pool()
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            """
            SELECT id, session_id, image_url, predicted_disease, predicted_confidence,
                   is_correct, corrected_disease, confirmed_label, comment,
                   verified_image_path, created_at
            FROM feedback
            WHERE user_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id, limit,
        )
        return [
            {
                "id": str(r["id"]),
                "session_id": r["session_id"],
                "image_url": r["image_url"],
                "predicted_disease": r["predicted_disease"],
                "predicted_confidence": float(r["predicted_confidence"]),
                "is_correct": r["is_correct"],
                "corrected_disease": r["corrected_disease"],
                "confirmed_label": r["confirmed_label"],
                "comment": r["comment"],
                "verified_image_path": r["verified_image_path"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    except Exception:
        logger.warning("Failed to fetch feedback history", exc_info=True)
        return []
