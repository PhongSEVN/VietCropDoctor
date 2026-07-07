from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Async Kafka producer wrapper with self-healing connect.

    Usage::

        producer = KafkaProducer(bootstrap_servers="kafka:29092", service="vision-ai")
        asyncio.create_task(producer.start())   # retries forever by default
        ...
        if producer.connected:
            await producer.publish(TOPIC_DISEASE_DETECTED, "disease.detected", payload)
        await producer.stop()

    `start()` retries with capped exponential backoff until connected, so a
    caller that fires it as a background task self-heals whether the broker
    is briefly unavailable at boot (e.g. topics not yet created) or goes down
    later. Pass `max_retries` > 0 to bound the attempts instead.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        service: str = "unknown",
        max_retries: int = 0,
        retry_backoff_secs: float = 1.0,
        max_backoff_secs: float = 30.0,
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._service = service
        self._max_retries = max_retries
        self._retry_backoff_secs = retry_backoff_secs
        self._max_backoff_secs = max_backoff_secs
        self._producer: AIOKafkaProducer | None = None
        self._connected = False
        self._stopped = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Connect to the broker, retrying with backoff until connected.

        Safe to run as a background task (`asyncio.create_task`) — cancel it
        to abort a pending retry, or call `stop()` once connected.
        """
        attempt = 0
        backoff = self._retry_backoff_secs
        while not self._stopped:
            try:
                producer = AIOKafkaProducer(
                    bootstrap_servers=self._bootstrap,
                    value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(),
                    acks="all",
                    enable_idempotence=True,
                    request_timeout_ms=10_000,
                    retry_backoff_ms=500,
                )
                await producer.start()
                self._producer = producer
                self._connected = True
                logger.info("KafkaProducer started (brokers=%s, service=%s)", self._bootstrap, self._service)
                return
            except Exception:
                attempt += 1
                if self._max_retries and attempt >= self._max_retries:
                    logger.error(
                        "KafkaProducer (%s) giving up after %d attempts", self._service, attempt
                    )
                    raise
                logger.warning(
                    "KafkaProducer (%s) connect failed (attempt %d), retrying in %.0fs",
                    self._service, attempt, backoff, exc_info=True,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_secs)

    async def stop(self) -> None:
        self._stopped = True
        self._connected = False
        if self._producer:
            await self._producer.stop()
            logger.info("KafkaProducer stopped")

    async def publish(self, topic: str, event_type: str, payload: dict) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaProducer not connected — check .connected before publish()")

        message = {
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self._service,
            "trace_id": str(uuid.uuid4()),
        }

        await self._producer.send_and_wait(topic, message)
        logger.debug("Published %s → %s", event_type, topic)
