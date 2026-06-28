"""
Sliding-window rate limiter backed by Redis sorted sets.

Algorithm per window:
  1. Remove entries older than (now - window_seconds)  [ZREMRANGEBYSCORE]
  2. Add current timestamp as a member                  [ZADD]
  3. Count entries in the window                        [ZCOUNT]
  4. Reset the key TTL                                  [EXPIRE]

All four steps run in a single pipeline for atomicity.
"""
from __future__ import annotations

import time
from typing import Optional


class RateLimiter:
    """Async Redis sliding-window rate limiter.

    Args:
        redis:          An initialised ``redis.asyncio.Redis`` instance.
        key_prefix:     Namespace prefix; the full key is ``{prefix}:{identifier}``.
        max_requests:   Maximum allowed requests per window.
        window_seconds: Width of the sliding window in seconds.

    Example::

        limiter = RateLimiter(redis, "rl:predict", max_requests=10, window_seconds=60)
        allowed = await limiter.check(user_id)
        if not allowed:
            raise HTTPException(429, "Too many requests")
    """

    def __init__(
        self,
        redis,
        key_prefix: str,
        max_requests: int,
        window_seconds: int,
    ) -> None:
        self.redis = redis
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def check(self, identifier: str) -> bool:
        """Return True if the request is within the rate limit, False otherwise.

        Always increments the counter — callers should check the return value
        and respond with 429 when False.
        """
        key = f"{self.key_prefix}:{identifier}"
        now = time.time()
        window_start = now - self.window_seconds

        # Use a unique score+member so two requests at the exact same millisecond
        # don't overwrite each other.
        member = f"{now:.6f}"

        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {member: now})
            pipe.zcount(key, window_start, "+inf")
            pipe.expire(key, self.window_seconds)
            results = await pipe.execute()

        count: int = results[2]
        return count <= self.max_requests

    async def remaining(self, identifier: str) -> int:
        """Return the number of requests remaining in the current window."""
        key = f"{self.key_prefix}:{identifier}"
        now = time.time()
        window_start = now - self.window_seconds
        count = await self.redis.zcount(key, window_start, "+inf")
        return max(0, self.max_requests - int(count))
