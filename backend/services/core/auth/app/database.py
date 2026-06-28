"""
PostgreSQL connection pool and schema initialisation.
"""
from __future__ import annotations

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialised — call init_pool() first")
    return _pool


async def init_pool() -> asyncpg.Pool:
    global _pool
    from app.config import get_settings
    settings = get_settings()
    _pool = await asyncpg.create_pool(
        settings.postgres_dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    logger.info("PostgreSQL connection pool created")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


async def run_migrations(pool: asyncpg.Pool) -> None:
    """Create schema if it doesn't exist."""
    await pool.execute("""
        CREATE EXTENSION IF NOT EXISTS "pgcrypto";

        CREATE TABLE IF NOT EXISTS users (
            id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            username      VARCHAR(50)  UNIQUE NOT NULL,
            email         VARCHAR(255),
            phone         VARCHAR(30),
            password_hash VARCHAR(255) NOT NULL,
            role          VARCHAR(20)  NOT NULL DEFAULT 'farmer'
                              CHECK (role IN ('farmer', 'agronomist', 'admin')),
            is_active     BOOLEAN      NOT NULL DEFAULT true,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users (email) WHERE email IS NOT NULL;

        -- Add new columns to existing tables (safe on repeat runs)
        ALTER TABLE users ADD COLUMN IF NOT EXISTS phone       VARCHAR(30);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();
        ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_path VARCHAR(500);

        CREATE TABLE IF NOT EXISTS chat_messages (
            id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id    UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id VARCHAR(64)  NOT NULL,
            disease    VARCHAR(255),
            question   TEXT         NOT NULL,
            answer     TEXT         NOT NULL,
            image_url  VARCHAR(1000),
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );

        -- Safe on existing deployments created before image_url was added.
        ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS image_url VARCHAR(1000);

        CREATE INDEX IF NOT EXISTS idx_chat_messages_user_id ON chat_messages (user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages (session_id);

        -- Diagnosis feedback — human-verified labels feeding the retraining loop.
        -- Created here (after users) so the FK resolves regardless of which
        -- service starts first. The RAG engine writes rows into this table.
        CREATE TABLE IF NOT EXISTS feedback (
            id                   UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id              UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id           VARCHAR(64),
            image_url            VARCHAR(1000),
            predicted_disease    VARCHAR(255) NOT NULL,
            predicted_confidence REAL         NOT NULL DEFAULT 0,
            is_correct           BOOLEAN      NOT NULL,
            corrected_disease    VARCHAR(255),
            confirmed_label      VARCHAR(255) NOT NULL,
            comment              TEXT,
            verified_image_path  VARCHAR(1000),
            created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );

        CREATE INDEX IF NOT EXISTS idx_feedback_user_id
            ON feedback (user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_confirmed_label
            ON feedback (confirmed_label);

        -- Admin dashboard columns: full name, login tracking, soft delete.
        ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name     VARCHAR(255);
        ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at    TIMESTAMPTZ;

        -- Admin audit trail — every privileged action is recorded server-side.
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id    UUID,
            actor_name  VARCHAR(100),
            action      VARCHAR(100) NOT NULL,
            target      VARCHAR(255),
            ip          VARCHAR(64),
            user_agent  VARCHAR(500),
            before_data JSONB,
            after_data  JSONB,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_action  ON audit_logs (action);

        -- Expert specialty/region assignment (admin-managed).
        CREATE TABLE IF NOT EXISTS expert_assignments (
            user_id    UUID        PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            crops      TEXT[]      NOT NULL DEFAULT '{}',
            regions    TEXT[]      NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        -- Admin broadcast notifications.
        CREATE TABLE IF NOT EXISTS notifications (
            id         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            title      VARCHAR(255) NOT NULL,
            body       TEXT         NOT NULL,
            audience   VARCHAR(20)  NOT NULL,
            group_role VARCHAR(20),
            sent_count INT          NOT NULL DEFAULT 0,
            created_by UUID,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications (created_at DESC);

        -- Expert review workflow on top of feedback cases.
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS status      VARCHAR(20) NOT NULL DEFAULT 'pending';
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS priority    VARCHAR(20) NOT NULL DEFAULT 'normal';
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS assignee_id UUID;
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS sla_due_at  TIMESTAMPTZ;
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW();
        -- Expert moderation: image flagged as not a crop leaf (irrelevant / OOD).
        ALTER TABLE feedback ADD COLUMN IF NOT EXISTS is_irrelevant BOOLEAN NOT NULL DEFAULT false;

        CREATE TABLE IF NOT EXISTS expert_responses (
            id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            feedback_id     UUID         NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
            expert_id       UUID         REFERENCES users(id) ON DELETE SET NULL,
            comment         TEXT         NOT NULL,
            diagnosis       VARCHAR(255),
            treatment       TEXT,
            attachment_urls TEXT[]       NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_expert_responses_fb ON expert_responses (feedback_id, created_at);

        CREATE TABLE IF NOT EXISTS internal_notes (
            id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
            feedback_id UUID         NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
            expert_id   UUID         REFERENCES users(id) ON DELETE SET NULL,
            note        TEXT         NOT NULL,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_internal_notes_fb ON internal_notes (feedback_id, created_at);
    """)
    logger.info("Schema migrations applied")
