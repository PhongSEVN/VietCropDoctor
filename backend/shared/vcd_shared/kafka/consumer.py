from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], Awaitable[None]]


class KafkaConsumer:
    """Async Kafka consumer wrapper with self-healing reconnect.

    Usage::

        consumer = KafkaConsumer(
            bootstrap_servers="kafka:29092",
            topics=[TOPIC_DISEASE_DETECTED],
            group_id="analytics-group",
        )
        consumer.subscribe(my_handler)
        task = asyncio.create_task(consumer.start())
        ...
        await consumer.stop()

    `start()` runs until `stop()` is called. If the broker connection drops or
    fails (including the broker being briefly unavailable at boot, e.g. topics
    not yet created), it retries with capped exponential backoff instead of
    letting the background task die permanently. Pass `max_retries` > 0 to
    bound the attempts instead of retrying forever.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topics: list[str],
        group_id: str,
        auto_offset_reset: str = "latest",
        max_retries: int = 0,
        retry_backoff_secs: float = 1.0,
        max_backoff_secs: float = 30.0,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._topics = topics
        self._group_id = group_id
        self._auto_offset_reset = auto_offset_reset
        self._max_retries = max_retries
        self._retry_backoff_secs = retry_backoff_secs
        self._max_backoff_secs = max_backoff_secs
        self._handlers: list[MessageHandler] = []
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def subscribe(self, handler: MessageHandler) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._running = True
        attempt = 0
        backoff = self._retry_backoff_secs
        while self._running:
            try:
                await self._consume_once()
                return  # _consume_once only returns normally after stop()
            except Exception:
                self._connected = False
                attempt += 1
                if self._max_retries and attempt >= self._max_retries:
                    logger.error(
                        "KafkaConsumer (group=%s) giving up after %d attempts",
                        self._group_id, attempt,
                    )
                    raise
                logger.warning(
                    "KafkaConsumer (group=%s) disconnected, retrying in %.0fs (attempt %d)",
                    self._group_id, backoff, attempt, exc_info=True,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_secs)

    async def _consume_once(self) -> None:
        consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            auto_offset_reset=self._auto_offset_reset,
            value_deserializer=lambda b: json.loads(b.decode()),
            enable_auto_commit=True,
        )
        await consumer.start()
        self._consumer = consumer
        self._connected = True
        logger.info(
            "KafkaConsumer started (group=%s topics=%s)",
            self._group_id,
            self._topics,
        )
        try:
            async for msg in consumer:
                if not self._running:
                    break
                for handler in self._handlers:
                    try:
                        await handler(msg.value)
                    except Exception:
                        logger.exception(
                            "Handler error for topic=%s offset=%s",
                            msg.topic,
                            msg.offset,
                        )
        finally:
            self._connected = False
            await consumer.stop()
            logger.info("KafkaConsumer stopped (group=%s)", self._group_id)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
