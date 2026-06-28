"""
Analytics query endpoints — read-only ClickHouse queries.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.queries import get_client
from app.config import JWT_SECRET, JWT_ALGORITHM

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def _user_id_from_token(token: str | None) -> str:
    if not token:
        return ""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return str(payload.get("sub", ""))
    except JWTError:
        return ""


# Response models

class DiseaseStat(BaseModel):
    disease: str
    count: int

class CropConfidence(BaseModel):
    crop: str
    avg_confidence: float

class SummaryResponse(BaseModel):
    today_count: int
    week_count: int
    month_count: int
    total_count: int
    top_diseases: list[DiseaseStat]
    avg_confidence_per_crop: list[CropConfidence]

class TrendPoint(BaseModel):
    date: str
    disease: str
    count: int

class TrendResponse(BaseModel):
    days: int
    data: list[TrendPoint]

class CropDistributionItem(BaseModel):
    crop: str
    count: int

class SeverityItem(BaseModel):
    crop: str
    severity: str
    count: int

class AlertItem(BaseModel):
    alert_id: str
    timestamp: str
    disease: str
    severity: str
    confidence: float
    crop: str

class HistoryItem(BaseModel):
    id: str
    created_at: str
    disease_class: str
    confidence: float
    severity: str
    crop: str
    image_url: Optional[str] = None


# Helpers

async def _query(sql: str) -> list[tuple]:
    try:
        client = await get_client()
        result = await client.query(sql)
        return result.result_rows
    except Exception as exc:
        logger.error("ClickHouse query failed: %s | SQL: %s", exc, sql[:200])
        raise HTTPException(status_code=503, detail="Analytics database unavailable")


# Endpoints

@router.get("/summary", response_model=SummaryResponse)
async def summary():
    counts_rows = await _query("""
        SELECT
            countIf(toDate(timestamp) = today())                          AS today_count,
            countIf(timestamp >= toStartOfWeek(now()))                    AS week_count,
            countIf(timestamp >= toStartOfMonth(now()))                   AS month_count,
            count(*)                                                      AS total_count
        FROM predictions
    """)
    today_count, week_count, month_count, total_count = (
        (counts_rows[0] if counts_rows else (0, 0, 0, 0))
    )

    top_rows = await _query("""
        SELECT disease, count(*) AS cnt
        FROM predictions
        WHERE timestamp >= now() - INTERVAL 30 DAY
        GROUP BY disease
        ORDER BY cnt DESC
        LIMIT 5
    """)

    conf_rows = await _query("""
        SELECT crop, round(avg(confidence), 4) AS avg_conf
        FROM predictions
        WHERE crop != ''
        GROUP BY crop
        ORDER BY crop
    """)

    return SummaryResponse(
        today_count=int(today_count),
        week_count=int(week_count),
        month_count=int(month_count),
        total_count=int(total_count),
        top_diseases=[DiseaseStat(disease=r[0], count=int(r[1])) for r in top_rows],
        avg_confidence_per_crop=[
            CropConfidence(crop=r[0], avg_confidence=float(r[1])) for r in conf_rows
        ],
    )


@router.get("/disease-trend", response_model=TrendResponse)
async def disease_trend(days: int = Query(default=30, ge=1, le=365)):
    rows = await _query(f"""
        SELECT
            toString(toDate(timestamp)) AS date,
            disease,
            count(*) AS cnt
        FROM predictions
        WHERE timestamp >= now() - INTERVAL {days} DAY
        GROUP BY date, disease
        ORDER BY date ASC, cnt DESC
    """)
    return TrendResponse(
        days=days,
        data=[TrendPoint(date=r[0], disease=r[1], count=int(r[2])) for r in rows],
    )


@router.get("/crop-distribution", response_model=list[CropDistributionItem])
async def crop_distribution():
    rows = await _query("""
        SELECT crop, count(*) AS cnt
        FROM predictions
        WHERE crop != ''
        GROUP BY crop
        ORDER BY cnt DESC
    """)
    return [CropDistributionItem(crop=r[0], count=int(r[1])) for r in rows]


@router.get("/severity-breakdown", response_model=list[SeverityItem])
async def severity_breakdown():
    rows = await _query("""
        SELECT crop, severity, count(*) AS cnt
        FROM predictions
        WHERE crop != '' AND severity != ''
        GROUP BY crop, severity
        ORDER BY crop ASC, cnt DESC
    """)
    return [SeverityItem(crop=r[0], severity=r[1], count=int(r[2])) for r in rows]


class ConfidenceBucketItem(BaseModel):
    bucket: str
    count: int


class RegionCountItem(BaseModel):
    region: str
    count: int


@router.get("/confidence-distribution", response_model=list[ConfidenceBucketItem])
async def confidence_distribution():
    """Distribution of prediction confidence into fixed 0.1-width buckets (ClickHouse)."""
    rows = await _query("""
        SELECT bucket, count(*) AS cnt FROM (
            SELECT multiIf(
                confidence < 0.5, '<0.5',
                confidence < 0.6, '0.5-0.6',
                confidence < 0.7, '0.6-0.7',
                confidence < 0.8, '0.7-0.8',
                confidence < 0.9, '0.8-0.9',
                '0.9-1.0') AS bucket
            FROM predictions
        )
        GROUP BY bucket
        ORDER BY bucket
    """)
    return [ConfidenceBucketItem(bucket=r[0], count=int(r[1])) for r in rows]


@router.get("/regions", response_model=list[RegionCountItem])
async def region_distribution():
    """Diagnoses by region. Region is not yet captured at upload time, so this
    returns an empty list until a region/geo column is added to the predictions
    schema (avoids a 404 so the UI shows a clean empty state)."""
    return []


@router.get("/alerts", response_model=list[AlertItem])
async def recent_alerts(limit: int = Query(default=50, ge=1, le=500)):
    rows = await _query(f"""
        SELECT
            toString(alert_id) AS alert_id,
            toString(timestamp) AS timestamp,
            disease,
            severity,
            confidence,
            crop
        FROM alerts
        ORDER BY timestamp DESC
        LIMIT {limit}
    """)
    return [
        AlertItem(
            alert_id=r[0],
            timestamp=r[1],
            disease=r[2],
            severity=r[3],
            confidence=float(r[4]),
            crop=r[5],
        )
        for r in rows
    ]


@router.get("/history/{entry_id}", response_model=HistoryItem)
async def diagnosis_history_entry(
    entry_id: str,
    x_user_id: str = Header(default="", alias="X-User-Id"),
    token: str | None = Depends(_oauth2),
):
    user_id = x_user_id or _user_id_from_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        client = await get_client()
        result = await client.query(
            """
            SELECT
                toString(event_id),
                toString(timestamp),
                disease,
                confidence,
                severity,
                crop,
                image_url
            FROM predictions
            WHERE user_id = {uid:String} AND event_id = {eid:String}
            LIMIT 1
            """,
            parameters={"uid": user_id, "eid": entry_id},
        )
        rows = result.result_rows
    except Exception as exc:
        logger.error("history entry query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Analytics database unavailable")

    if not rows:
        raise HTTPException(status_code=404, detail="Entry not found")
    r = rows[0]
    return HistoryItem(
        id=r[0],
        created_at=r[1],
        disease_class=r[2],
        confidence=float(r[3]),
        severity=r[4] or "mild",
        crop=r[5],
        image_url=r[6] if len(r) > 6 else None,
    )


@router.get("/history", response_model=list[HistoryItem])
async def diagnosis_history(
    limit: int = Query(default=20, ge=1, le=100),
    x_user_id: str = Header(default="", alias="X-User-Id"),
    token: str | None = Depends(_oauth2),
):
    user_id = x_user_id or _user_id_from_token(token)
    if not user_id:
        return []
    try:
        client = await get_client()
        result = await client.query(
            """
            SELECT
                toString(event_id),
                toString(timestamp),
                disease,
                confidence,
                severity,
                crop
            FROM predictions
            WHERE user_id = {uid:String}
            ORDER BY timestamp DESC
            LIMIT {lim:UInt32}
            """,
            parameters={"uid": user_id, "lim": limit},
        )
        rows = result.result_rows
    except Exception as exc:
        logger.error("history query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Analytics database unavailable")

    return [
        HistoryItem(
            id=r[0],
            created_at=r[1],
            disease_class=r[2],
            confidence=float(r[3]),
            severity=r[4] or "mild",
            crop=r[5],
        )
        for r in rows
    ]
