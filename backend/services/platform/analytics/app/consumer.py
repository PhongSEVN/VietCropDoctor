"""
Kafka → ClickHouse ingestion for analytics events.

Each topic maps to a BatchBuffer that accumulates rows and flushes to ClickHouse
when either 100 rows accumulate or 5 seconds elapse, whichever comes first.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable

from vcd_shared.kafka import (
    TOPIC_CHAT_REQUESTED,
    TOPIC_DISEASE_DETECTED,
    TOPIC_FEEDBACK_SUBMITTED,
    TOPIC_RETRAIN_REQUESTED,
    KafkaConsumer,
    KafkaProducer,
)

from app.config import (
    AIRFLOW_PASSWORD,
    AIRFLOW_URL,
    AIRFLOW_USERNAME,
    BATCH_FLUSH_SECS,
    BATCH_MAX_ROWS,
    KAFKA_BOOTSTRAP_SERVERS,
    RETRAIN_DAG,
    RETRAIN_FEEDBACK_THRESHOLD,
)
from app.queries import get_client

logger = logging.getLogger(__name__)

_CROP_MAP: dict[str, str] = {
    "cafe": "Cà phê", "coffee": "Cà phê",
    "lua":  "Lúa",    "rice":   "Lúa",
    "mia":  "Mía",    "sugarcane": "Mía",
    "ngo":  "Ngô",    "corn":   "Ngô",
}


def _extract_crop(disease: str) -> str:
    return _CROP_MAP.get(disease.split("_")[0].lower(), "Khác")


def _parse_ts(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        return datetime.fromisoformat(raw.rstrip("Z")).replace(tzinfo=None)
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)


# Batch buffer

class BatchBuffer:
    """Accumulates rows and flushes to ClickHouse in batches."""

    def __init__(self, table: str, columns: list[str]) -> None:
        self._table   = table
        self._columns = columns
        self._rows:  list[tuple] = []
        self._lock   = asyncio.Lock()

    async def add(self, row: tuple) -> None:
        async with self._lock:
            self._rows.append(row)
            if len(self._rows) >= BATCH_MAX_ROWS:
                await self._do_flush()

    async def flush(self) -> None:
        async with self._lock:
            await self._do_flush()

    async def _do_flush(self) -> None:
        if not self._rows:
            return
        rows, self._rows = self._rows[:], []
        try:
            client = await get_client()
            await client.insert(self._table, rows, column_names=self._columns)
            logger.debug("Flushed %d rows → %s", len(rows), self._table)
        except Exception as exc:
            logger.error("ClickHouse insert failed (%s): %s", self._table, exc)

    async def run_timer(self) -> None:
        """Background task: flush every BATCH_FLUSH_SECS seconds."""
        while True:
            await asyncio.sleep(BATCH_FLUSH_SECS)
            await self.flush()


# Buffers (one per table)

_predictions_buf = BatchBuffer(
    table="predictions",
    columns=[
        "event_id", "timestamp", "disease", "confidence",
        "severity", "crop", "session_id", "latency_ms",
        "ensemble_used", "agreement_score", "user_id",
    ],
)

_chat_buf = BatchBuffer(
    table="chat_events",
    columns=[
        "event_id", "timestamp", "session_id", "disease",
        "question", "answer_len", "retrieved_chunks", "latency_ms",
    ],
)

_feedback_buf = BatchBuffer(
    table="feedback_events",
    columns=[
        "event_id", "timestamp", "feedback_id", "user_id",
        "predicted_disease", "is_correct", "corrected_disease",
        "confirmed_label", "crop",
    ],
)

_ALL_BUFFERS = [_predictions_buf, _chat_buf, _feedback_buf]


# Kafka handlers

async def _on_disease_detected(msg: dict) -> None:
    payload = msg.get("payload", {})
    disease = payload.get("disease", "unknown")
    row = (
        str(uuid.uuid4()),
        _parse_ts(msg.get("timestamp")),
        disease,
        float(payload.get("confidence", 0.0)),
        payload.get("severity", ""),
        _extract_crop(disease),
        payload.get("session_id", ""),
        float(payload.get("latency_ms", 0.0)),
        int(bool(payload.get("ensemble_used", False))),
        float(payload.get("agreement_score", 1.0)),
        payload.get("user_id", ""),
    )
    await _predictions_buf.add(row)


async def _on_chat_requested(msg: dict) -> None:
    payload = msg.get("payload", {})
    question = payload.get("question", "")
    row = (
        str(uuid.uuid4()),
        _parse_ts(msg.get("timestamp")),
        payload.get("session_id", ""),
        payload.get("disease_filter", ""),
        question[:2000],
        int(payload.get("answer_len", len(payload.get("answer", "")))),
        int(payload.get("retrieved_chunks", 0)),
        float(payload.get("latency_ms", 0.0)),
    )
    await _chat_buf.add(row)


# Retrain loop (gap: feedback.submitted + retrain.requested)

_producer: KafkaProducer | None = None
_feedback_seen = 0  # in-memory counter since startup; resets on restart


async def _on_feedback_submitted(msg: dict) -> None:
    """Persist a human feedback event to ClickHouse and, every Nth event, ask the
    ML pipeline to retrain by publishing retrain.requested."""
    global _feedback_seen
    payload = msg.get("payload", {})
    predicted = payload.get("predicted_disease", "unknown")
    row = (
        str(uuid.uuid4()),
        _parse_ts(msg.get("timestamp")),
        str(payload.get("feedback_id", "")),
        str(payload.get("user_id", "")),
        predicted,
        int(bool(payload.get("is_correct", False))),
        payload.get("corrected_disease") or "",
        payload.get("confirmed_label") or "",
        _extract_crop(predicted),
    )
    await _feedback_buf.add(row)

    _feedback_seen += 1
    if (
        _producer and _producer.connected
        and RETRAIN_FEEDBACK_THRESHOLD > 0
        and _feedback_seen % RETRAIN_FEEDBACK_THRESHOLD == 0
    ):
        try:
            await _producer.publish(
                topic=TOPIC_RETRAIN_REQUESTED,
                event_type="retrain.requested",
                payload={
                    "reason": "feedback_threshold",
                    "feedback_count": _feedback_seen,
                    "threshold": RETRAIN_FEEDBACK_THRESHOLD,
                },
            )
            logger.info("Published retrain.requested (feedback_count=%d)", _feedback_seen)
        except Exception:
            logger.warning("Failed to publish retrain.requested", exc_info=True)


def _trigger_airflow_dag() -> str:
    """Synchronously trigger the Airflow retrain DAG. Returns the dag_run id or ''."""
    url = f"{AIRFLOW_URL}/api/v1/dags/{RETRAIN_DAG}/dagRuns"
    auth = base64.b64encode(f"{AIRFLOW_USERNAME}:{AIRFLOW_PASSWORD}".encode()).decode()
    data = json.dumps({"conf": {"source": "kafka.retrain_requested"}}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Basic {auth}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode() or "{}")
    return str(body.get("dag_run_id", ""))


async def _on_retrain_requested(msg: dict) -> None:
    """Consume retrain.requested and trigger the Airflow DAG (the documented
    Kafka → Airflow handoff). Failures are logged, never fatal."""
    payload = msg.get("payload", {})
    logger.info("retrain.requested received: %s", payload)
    try:
        run_id = await asyncio.to_thread(_trigger_airflow_dag)
        logger.info("Airflow retrain DAG triggered (dag_run_id=%s)", run_id or "?")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            logger.warning(
                "Airflow auth required — set AIRFLOW_USERNAME/PASSWORD for analytics "
                "to enable auto-retrain. Event logged but DAG not triggered."
            )
        else:
            logger.warning("Airflow returned %s when triggering retrain", exc.code)
    except Exception:
        logger.warning("Failed to trigger Airflow retrain DAG", exc_info=True)


# Lifecycle

_consumers:    list[tuple[str, KafkaConsumer]] = []
_tasks:        list[asyncio.Task]   = []


def kafka_status() -> dict:
    """Live Kafka connectivity, exposed via /health so a dead producer/consumer
    is visible to monitoring instead of only surfacing as a WARNING log line."""
    return {
        "producer_connected": bool(_producer and _producer.connected),
        "consumers": {topic: c.connected for topic, c in _consumers},
    }


async def start() -> None:
    global _producer
    # Producer used to emit retrain.requested when the feedback threshold is hit.
    # Connects in the background — self-heals via retry/backoff instead of
    # giving up forever if Kafka isn't reachable yet at startup.
    _producer = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS, service="analytics")
    _tasks.append(asyncio.create_task(_producer.start(), name="kafka-producer-connect"))

    topic_map: list[tuple[str, str, Callable[[dict], Awaitable[None]]]] = [
        (TOPIC_DISEASE_DETECTED,  "analytics-disease-group",  _on_disease_detected),
        (TOPIC_CHAT_REQUESTED,    "analytics-chat-group",     _on_chat_requested),
        (TOPIC_FEEDBACK_SUBMITTED, "analytics-feedback-group", _on_feedback_submitted),
        (TOPIC_RETRAIN_REQUESTED, "analytics-retrain-group",  _on_retrain_requested),
    ]

    for topic, group_id, handler in topic_map:
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            topics=[topic],
            group_id=group_id,
        )
        consumer.subscribe(handler)
        _consumers.append((topic, consumer))
        _tasks.append(asyncio.create_task(consumer.start(), name=f"consumer:{topic}"))
        logger.info("Consumer starting for topic=%s", topic)

    # Timer flush tasks — one per buffer
    for buf in _ALL_BUFFERS:
        _tasks.append(asyncio.create_task(buf.run_timer(), name=f"flush:{buf._table}"))


async def stop() -> None:
    for _, consumer in _consumers:
        await consumer.stop()

    for task in _tasks:
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
    _tasks.clear()
    _consumers.clear()

    for buf in _ALL_BUFFERS:
        await buf.flush()

    global _producer
    if _producer:
        await _producer.stop()
        _producer = None
    logger.info("Analytics consumers stopped, buffers flushed")
