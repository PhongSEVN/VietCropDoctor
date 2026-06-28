from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], Awaitable[None]]


class KafkaConsumer:
    """Async Kafka consumer wrapper.

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
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topics: list[str],
        group_id: str,
        auto_offset_reset: str = "latest",
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._topics = topics
        self._group_id = group_id
        self._auto_offset_reset = auto_offset_reset
        self._handlers: list[MessageHandler] = []
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    def subscribe(self, handler: MessageHandler) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            auto_offset_reset=self._auto_offset_reset,
            value_deserializer=lambda b: json.loads(b.decode()),
            enable_auto_commit=True,
        )
        await self._consumer.start()
        self._running = True
        logger.info(
            "KafkaConsumer started (group=%s topics=%s)",
            self._group_id,
            self._topics,
        )
        try:
            async for msg in self._consumer:
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
            await self._consumer.stop()
            logger.info("KafkaConsumer stopped (group=%s)", self._group_id)

    async def stop(self) -> None:
        self._running = False
        if self._consumer:
            await self._consumer.stop()
