from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class KafkaProducer:
    """Async Kafka producer wrapper.

    Usage::

        producer = KafkaProducer(bootstrap_servers="kafka:29092", service="vision-ai")
        await producer.start()
        await producer.publish(TOPIC_DISEASE_DETECTED, "disease.detected", payload)
        await producer.stop()
    """

    def __init__(self, bootstrap_servers: str, service: str = "unknown") -> None:
        self._bootstrap = bootstrap_servers
        self._service = service
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(),
            acks="all",
            enable_idempotence=True,
            request_timeout_ms=10_000,
            retry_backoff_ms=500,
        )
        await self._producer.start()
        logger.info("KafkaProducer started (brokers=%s)", self._bootstrap)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            logger.info("KafkaProducer stopped")

    async def publish(self, topic: str, event_type: str, payload: dict) -> None:
        if self._producer is None:
            raise RuntimeError("KafkaProducer not started — call await producer.start() first")

        message = {
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self._service,
            "trace_id": str(uuid.uuid4()),
        }

        await self._producer.send_and_wait(topic, message)
        logger.debug("Published %s → %s", event_type, topic)
