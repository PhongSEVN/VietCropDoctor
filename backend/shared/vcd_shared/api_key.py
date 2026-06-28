"""
Service-to-service API key validation.

Keys are stored in Redis as:  ``apikey:{key}`` → ``{source_service_name}``

Provision a key (one-time setup):
    redis-cli SET apikey:$(openssl rand -hex 32) "vision-ai"

Usage in a FastAPI service::

    from vcd_shared.api_key import ApiKeyValidator

    # At module level, after Redis client is initialised:
    validate_api_key = ApiKeyValidator(lambda: redis_client)

    @app.post("/internal-endpoint")
    async def handler(source: str = Depends(validate_api_key)):
        # source is the registered service name, e.g. "vision-ai"
        ...
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


class ApiKeyValidator:
    """FastAPI dependency class for X-API-Key header validation.

    Args:
        get_redis: Zero-argument callable that returns a ``redis.asyncio.Redis``
                   instance (or coroutine that returns one).  Called on each
                   request so the service controls connection lifecycle.
    """

    def __init__(self, get_redis: Callable) -> None:
        self._get_redis = get_redis

    async def __call__(
        self,
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    ) -> Optional[str]:
        """Return the registered source service name, or None if no key provided.

        Raises HTTPException 401 when a key is present but invalid.
        """
        if x_api_key is None:
            return None

        redis = self._get_redis()
        # Support both sync return and coroutine
        if hasattr(redis, "__await__"):
            redis = await redis

        raw = await redis.get(f"apikey:{x_api_key}")
        if raw is None:
            logger.warning("Invalid API key presented (last 8 chars: ...%s)", x_api_key[-8:])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        source = raw if isinstance(raw, str) else raw.decode()
        logger.debug("API key accepted from service=%s", source)
        return source
