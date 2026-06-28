"""
ClickHouse client — async, shared singleton.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import clickhouse_connect

from app.config import (
    CLICKHOUSE_DB,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USER,
)

logger = logging.getLogger(__name__)

_client: clickhouse_connect.driver.AsyncClient | None = None


async def get_client() -> clickhouse_connect.driver.AsyncClient:
    global _client
    if _client is None:
        _client = await clickhouse_connect.get_async_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )
    return _client


async def init_schema(retries: int = 10, delay: float = 3.0) -> None:
    """Execute schema.sql to create tables. Retries while ClickHouse warms up."""
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text()

    for attempt in range(retries):
        try:
            client = await get_client()
            for stmt in sql.split(";"):
                lines = [
                    line for line in stmt.splitlines()
                    if line.strip() and not line.strip().startswith("--")
                ]
                clean = "\n".join(lines).strip()
                if clean:
                    await client.command(clean)
            logger.info("ClickHouse schema ready")
            return
        except Exception as exc:
            logger.warning(
                "ClickHouse not ready (attempt %d/%d): %s", attempt + 1, retries, exc
            )
            if attempt < retries - 1:
                await asyncio.sleep(delay)

    raise RuntimeError("Could not connect to ClickHouse after %d attempts" % retries)
