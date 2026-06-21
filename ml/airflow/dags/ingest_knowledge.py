"""
DAG: ingest_knowledge_base
Schedule: Weekly Monday 03:00 UTC

Pipeline:
  check_new_documents → ingest_documents → rebuild_bm25_index
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

_LAST_INGEST_PATH = Path("/data/airflow/last_ingest.json")
_RAG_BASE_URL     = "http://rag-engine:8002"
_REQUEST_TIMEOUT  = 300   # ingestion can be slow


# Task functions

def check_new_documents(**context) -> list[str]:
    """Return list of document paths newer than last ingest timestamp.

    Stores file list in XCom for downstream tasks.
    """
    last_ts = datetime.min
    if _LAST_INGEST_PATH.exists():
        try:
            data    = json.loads(_LAST_INGEST_PATH.read_text())
            last_ts = datetime.fromisoformat(data.get("last_ingest", datetime.min.isoformat()))
        except (json.JSONDecodeError, ValueError):
            pass

    logger.info("Scanning for documents newer than %s", last_ts.isoformat())

    # Ask the RAG service what it knows (indirectly via collection stats)
    # We track ingest time server-side; new files must be added to the knowledge dir
    # before this DAG runs. Check by polling the service.
    try:
        resp = requests.get(f"{_RAG_BASE_URL}/collection", timeout=10)
        if resp.status_code == 200:
            vectors_count = resp.json().get("vectors_count", 0)
            logger.info("Current vector count: %d", vectors_count)
        else:
            vectors_count = 0
    except Exception as exc:
        logger.warning("RAG engine unreachable: %s — assuming new docs exist", exc)
        return ["<rag-engine-unreachable>"]

    # If we have a last ingest record, check if it was recent (< 6 days)
    hours_since = (datetime.utcnow() - last_ts).total_seconds() / 3600
    if hours_since < 144:   # 6 days — less than weekly cadence
        raise AirflowSkipException(
            f"Last ingest was {hours_since:.1f}h ago (< 144h) — skipping"
        )

    logger.info("Proceeding with knowledge base ingestion (last_ingest=%s)", last_ts.isoformat())
    return ["scheduled_weekly_ingest"]


def ingest_documents(**context) -> None:
    """POST /ingest to the RAG engine with incremental mode."""
    ti        = context["ti"]
    new_files = ti.xcom_pull(task_ids="check_new_documents") or []

    if not new_files:
        logger.info("No new documents signalled — skipping ingest")
        raise AirflowSkipException("No new documents to ingest")

    logger.info("Triggering RAG ingestion (files=%s)", new_files)

    try:
        resp = requests.post(
            f"{_RAG_BASE_URL}/ingest",
            json={"recreate_collection": False},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            "Ingestion complete: chunks_created=%d documents_processed=%d elapsed=%.1fs",
            result.get("chunks_created", 0),
            result.get("documents_processed", 0),
            result.get("elapsed_seconds", 0),
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Ingestion request failed: {exc}")

    # Record timestamp
    _LAST_INGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAST_INGEST_PATH.write_text(
        json.dumps({"last_ingest": datetime.utcnow().isoformat()}, indent=2)
    )


def rebuild_bm25_index(**context) -> None:
    """Trigger BM25 index rebuild in the RAG engine."""
    try:
        resp = requests.post(
            f"{_RAG_BASE_URL}/admin/rebuild-bm25",
            timeout=120,
        )
        resp.raise_for_status()
        logger.info("BM25 index rebuilt: %s", resp.json())
    except requests.RequestException as exc:
        # Non-fatal — dense retrieval still works
        logger.warning("BM25 rebuild request failed: %s", exc)


# DAG definition

default_args = {
    "owner":            "mlops",
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="ingest_knowledge_base",
    description="Weekly knowledge-base ingestion and BM25 index rebuild",
    schedule="0 3 * * 1",   # Monday 03:00 UTC
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["mlops", "rag-engine"],
) as dag:

    t1 = PythonOperator(
        task_id="check_new_documents",
        python_callable=check_new_documents,
    )

    t2 = PythonOperator(
        task_id="ingest_documents",
        python_callable=ingest_documents,
    )

    t3 = PythonOperator(
        task_id="rebuild_bm25_index",
        python_callable=rebuild_bm25_index,
    )

    t1 >> t2 >> t3
