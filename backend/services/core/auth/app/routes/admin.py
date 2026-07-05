"""
Admin router — user management, audit trail, and KPIs.

Mounted at /admin (the gateway exposes it as /api/admin/* behind
auth_request /auth-validate-admin). Defense-in-depth: require_admin re-verifies
the JWT role here too, so a direct hit without the gateway is still gated.

Owns the `users` table (PostgreSQL). Every mutating action writes an audit_logs
row as the server-side source of truth.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

import csv
import io

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from vcd_shared.auth import hash_password, verify_token
from app.config import get_settings
from app.database import get_pool
from app.minio_client import AVATAR_BUCKET
from app.admin_models import (
    AddExpertBody,
    AdminKpisOut,
    AdminUserOut,
    AssignExpertBody,
    AuditCreateBody,
    AuditLogOut,
    CreateUserBody,
    ExpertProfileOut,
    ModelRun,
    NotificationBody,
    NotificationResult,
    PaginatedAudit,
    PaginatedUsers,
    RetrainBody,
    UpdateUserBody,
    UserGrowthPoint,
)

logger = logging.getLogger("auth.admin")
router = APIRouter(prefix="/admin", tags=["admin"])

_ROLES = ("farmer", "agronomist", "admin")
USER_COLS = (
    "id, username, full_name, email, phone, avatar_path, "
    "role, is_active, deleted_at, created_at, last_login_at"
)


# RBAC

def require_admin(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    payload = verify_token(authorization.removeprefix("Bearer ").strip())
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return payload


# Mappers

def _avatar_url(avatar_path: Optional[str]) -> Optional[str]:
    if not avatar_path:
        return None
    return f"{get_settings().minio_public_url}/{AVATAR_BUCKET}/{avatar_path}"


def _status(row: asyncpg.Record) -> str:
    if row["deleted_at"] is not None:
        return "deleted"
    return "active" if row["is_active"] else "locked"


def _user_out(row: asyncpg.Record) -> AdminUserOut:
    return AdminUserOut(
        id=str(row["id"]),
        username=row["username"],
        full_name=row["full_name"],
        email=row["email"],
        phone=row["phone"],
        avatar_url=_avatar_url(row["avatar_path"]),
        role=row["role"],
        status=_status(row),
        created_at=row["created_at"].isoformat(),
        last_login_at=row["last_login_at"].isoformat() if row["last_login_at"] else None,
    )


async def _audit(
    pool: asyncpg.Pool,
    actor: dict,
    action: str,
    target: Optional[str] = None,
    before: object = None,
    after: object = None,
    request: Optional[Request] = None,
) -> None:
    ip = request.client.host if request and request.client else None
    ua = request.headers.get("user-agent") if request else None
    try:
        await pool.execute(
            """
            INSERT INTO audit_logs
                (actor_id, actor_name, action, target, ip, user_agent, before_data, after_data)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
            """,
            actor.get("sub"),
            actor.get("username"),
            action,
            target,
            ip,
            ua,
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
        )
    except Exception:  # noqa: BLE001 — auditing must never break the action
        logger.warning("Failed to write audit log for %s", action, exc_info=True)


async def _fetch_user(pool: asyncpg.Pool, user_id: str) -> asyncpg.Record:
    row = await pool.fetchrow(f"SELECT {USER_COLS} FROM users WHERE id = $1::uuid", user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


# User management

@router.get("/users", response_model=PaginatedUsers)
async def list_users(
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
    search: str = Query(""),
    role: str = Query("all"),
    status_filter: str = Query("all", alias="status"),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    where: list[str] = []
    args: list[object] = []

    if search.strip():
        args.append(f"%{search.strip().lower()}%")
        i = len(args)
        where.append(
            f"(lower(username) LIKE ${i} OR lower(coalesce(email,'')) LIKE ${i} "
            f"OR lower(coalesce(full_name,'')) LIKE ${i} OR coalesce(phone,'') LIKE ${i})"
        )
    if role in _ROLES:
        args.append(role)
        where.append(f"role = ${len(args)}")
    if status_filter == "active":
        where.append("is_active AND deleted_at IS NULL")
    elif status_filter == "locked":
        where.append("NOT is_active AND deleted_at IS NULL")
    elif status_filter == "deleted":
        where.append("deleted_at IS NOT NULL")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order = {
        "newest": "created_at DESC",
        "oldest": "created_at ASC",
        "name": "username ASC",
        "last_login": "last_login_at DESC NULLS LAST",
    }.get(sort, "created_at DESC")

    total = await pool.fetchval(f"SELECT count(*) FROM users {where_sql}", *args)
    offset = (page - 1) * page_size
    rows = await pool.fetch(
        f"SELECT {USER_COLS} FROM users {where_sql} "
        f"ORDER BY {order} LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}",
        *args, page_size, offset,
    )
    return PaginatedUsers(
        items=[_user_out(r) for r in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserBody,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    if body.role not in _ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")
    if await pool.fetchrow("SELECT id FROM users WHERE username = $1", body.username):
        raise HTTPException(status_code=400, detail="Username already taken")

    row = await pool.fetchrow(
        f"""
        INSERT INTO users (username, email, phone, full_name, password_hash, role)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING {USER_COLS}
        """,
        body.username, body.email, body.phone, body.full_name,
        hash_password(body.password), body.role,
    )
    out = _user_out(row)
    await _audit(pool, admin, "user.create", out.id, None,
                 {"username": body.username, "role": body.role}, request)
    return out


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: str,
    body: UpdateUserBody,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    before = await _fetch_user(pool, user_id)

    sets: list[str] = []
    args: list[object] = []
    for field in ("email", "phone", "full_name", "role"):
        val = getattr(body, field)
        if val is not None:
            if field == "role" and val not in _ROLES:
                raise HTTPException(status_code=422, detail="Invalid role")
            args.append(val)
            sets.append(f"{field} = ${len(args)}")

    if not sets:
        return _user_out(before)

    args.append(user_id)
    row = await pool.fetchrow(
        f"UPDATE users SET {', '.join(sets)}, updated_at = NOW() "
        f"WHERE id = ${len(args)}::uuid RETURNING {USER_COLS}",
        *args,
    )
    action = "user.role_change" if body.role is not None and len(sets) == 1 else "user.update"
    await _audit(pool, admin, action, user_id, _user_out(before).model_dump(),
                 _user_out(row).model_dump(), request)
    return _user_out(row)


async def _set_state(
    pool: asyncpg.Pool, user_id: str, set_sql: str,
    admin: dict, action: str, request: Request,
) -> AdminUserOut:
    before = await _fetch_user(pool, user_id)
    row = await pool.fetchrow(
        f"UPDATE users SET {set_sql}, updated_at = NOW() WHERE id = $1::uuid RETURNING {USER_COLS}",
        user_id,
    )
    await _audit(pool, admin, action, user_id, _user_out(before).model_dump(),
                 _user_out(row).model_dump(), request)
    return _user_out(row)


@router.post("/users/{user_id}/lock", response_model=AdminUserOut)
async def lock_user(user_id: str, request: Request,
                    admin: dict = Depends(require_admin), pool: asyncpg.Pool = Depends(get_pool)):
    return await _set_state(pool, user_id, "is_active = false", admin, "user.lock", request)


@router.post("/users/{user_id}/unlock", response_model=AdminUserOut)
async def unlock_user(user_id: str, request: Request,
                      admin: dict = Depends(require_admin), pool: asyncpg.Pool = Depends(get_pool)):
    return await _set_state(pool, user_id, "is_active = true", admin, "user.unlock", request)


@router.delete("/users/{user_id}", response_model=AdminUserOut)
async def soft_delete_user(user_id: str, request: Request,
                           admin: dict = Depends(require_admin), pool: asyncpg.Pool = Depends(get_pool)):
    return await _set_state(pool, user_id, "deleted_at = NOW(), is_active = false",
                            admin, "user.soft_delete", request)


@router.post("/users/{user_id}/restore", response_model=AdminUserOut)
async def restore_user(user_id: str, request: Request,
                       admin: dict = Depends(require_admin), pool: asyncpg.Pool = Depends(get_pool)):
    return await _set_state(pool, user_id, "deleted_at = NULL, is_active = true",
                            admin, "user.restore", request)


# Audit

@router.get("/audit", response_model=PaginatedAudit)
async def list_audit(
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
    search: str = Query(""),
    action: str = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    where: list[str] = []
    args: list[object] = []
    if search.strip():
        args.append(f"%{search.strip().lower()}%")
        i = len(args)
        where.append(f"(lower(coalesce(actor_name,'')) LIKE ${i} OR lower(action) LIKE ${i} OR lower(coalesce(target,'')) LIKE ${i})")
    if action != "all":
        args.append(action)
        where.append(f"action = ${len(args)}")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = await pool.fetchval(f"SELECT count(*) FROM audit_logs {where_sql}", *args)
    offset = (page - 1) * page_size
    rows = await pool.fetch(
        f"SELECT * FROM audit_logs {where_sql} ORDER BY created_at DESC "
        f"LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}",
        *args, page_size, offset,
    )

    def _parse(v):
        if v is None:
            return None
        return json.loads(v) if isinstance(v, str) else v

    items = [
        AuditLogOut(
            id=str(r["id"]),
            actor_id=str(r["actor_id"]) if r["actor_id"] else None,
            actor_name=r["actor_name"],
            action=r["action"],
            target=r["target"],
            timestamp=r["created_at"].isoformat(),
            ip=r["ip"],
            user_agent=r["user_agent"],
            before=_parse(r["before_data"]),
            after=_parse(r["after_data"]),
        )
        for r in rows
    ]
    return PaginatedAudit(items=items, total=int(total or 0), page=page, page_size=page_size)


@router.post("/audit")
async def add_audit(
    body: AuditCreateBody,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    await _audit(pool, admin, body.action, body.target, body.before, body.after, request)
    return {"ok": True}


# KPIs

@router.get("/kpis", response_model=AdminKpisOut)
async def kpis(admin: dict = Depends(require_admin), pool: asyncpg.Pool = Depends(get_pool)):
    total_users = await pool.fetchval("SELECT count(*) FROM users WHERE deleted_at IS NULL")
    new_today = await pool.fetchval("SELECT count(*) FROM users WHERE created_at >= date_trunc('day', now())")
    new_week = await pool.fetchval("SELECT count(*) FROM users WHERE created_at >= now() - interval '7 days'")
    new_month = await pool.fetchval("SELECT count(*) FROM users WHERE created_at >= now() - interval '30 days'")
    dau = await pool.fetchval("SELECT count(*) FROM users WHERE last_login_at >= date_trunc('day', now())")
    wau = await pool.fetchval("SELECT count(*) FROM users WHERE last_login_at >= now() - interval '7 days'")
    mau = await pool.fetchval("SELECT count(*) FROM users WHERE last_login_at >= now() - interval '30 days'")

    total_feedback = await pool.fetchval("SELECT count(*) FROM feedback")
    total_images = await pool.fetchval("SELECT count(*) FROM feedback WHERE image_url IS NOT NULL")
    total_expert_responses = await pool.fetchval("SELECT count(*) FROM expert_responses")
    # Every RAG/LLM answer turn is an AI inference event; expert-reply rows are
    # injected (not AI) and excluded. Diagnoses (with image) are counted too.
    total_ai_analyses = await pool.fetchval(
        "SELECT count(*) FROM chat_messages WHERE question <> '__EXPERT_REPLY__'"
    )

    retention = (wau / mau) if mau else None
    churn = (1 - retention) if retention is not None else None

    return AdminKpisOut(
        total_users=int(total_users or 0),
        new_today=int(new_today or 0),
        new_week=int(new_week or 0),
        new_month=int(new_month or 0),
        dau=int(dau or 0),
        wau=int(wau or 0),
        mau=int(mau or 0),
        retention_rate=round(retention, 4) if retention is not None else None,
        churn_rate=round(churn, 4) if churn is not None else None,
        total_feedback=int(total_feedback or 0),
        total_images=int(total_images or 0),
        total_ai_analyses=int(total_ai_analyses or 0),
        total_expert_responses=int(total_expert_responses or 0),
    )


# Experts

_EXPERT_SELECT = """
    SELECT u.id, u.username, u.full_name,
           coalesce(a.crops, '{}')   AS crops,
           coalesce(a.regions, '{}') AS regions,
           (SELECT count(DISTINCT er.feedback_id) FROM expert_responses er
                WHERE er.expert_id = u.id) AS handled_cases,
           (SELECT count(DISTINCT er.feedback_id) FROM expert_responses er
                JOIN feedback f ON f.id = er.feedback_id
                WHERE er.expert_id = u.id AND f.status = 'answered') AS answered_cases,
           (SELECT avg(extract(epoch FROM (er.created_at - f.created_at)) / 60.0)
                FROM expert_responses er JOIN feedback f ON f.id = er.feedback_id
                WHERE er.expert_id = u.id) AS avg_minutes
    FROM users u
    LEFT JOIN expert_assignments a ON a.user_id = u.id
"""


def _expert_out(row: asyncpg.Record) -> ExpertProfileOut:
    # Real performance from expert_responses; rating + presence still TODO.
    handled = int(row["handled_cases"] or 0)
    answered = int(row["answered_cases"] or 0)
    avg_min = row["avg_minutes"]
    return ExpertProfileOut(
        id=str(row["id"]),
        name=row["full_name"] or row["username"],
        handled_cases=handled,
        completion_rate=round(answered / handled, 4) if handled else 0.0,
        avg_response_minutes=round(float(avg_min), 1) if avg_min is not None else None,
        crops=list(row["crops"]),
        regions=list(row["regions"]),
    )


@router.get("/experts", response_model=list[ExpertProfileOut])
async def list_experts(admin: dict = Depends(require_admin), pool: asyncpg.Pool = Depends(get_pool)):
    rows = await pool.fetch(
        _EXPERT_SELECT + " WHERE u.role = 'agronomist' AND u.deleted_at IS NULL ORDER BY u.created_at DESC"
    )
    return [_expert_out(r) for r in rows]


@router.post("/experts", response_model=ExpertProfileOut, status_code=status.HTTP_201_CREATED)
async def add_expert(
    body: AddExpertBody,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    before = await pool.fetchrow("SELECT role FROM users WHERE id = $1::uuid AND deleted_at IS NULL", body.user_id)
    if not before:
        raise HTTPException(status_code=404, detail="User not found")
    await pool.execute("UPDATE users SET role = 'agronomist', updated_at = NOW() WHERE id = $1::uuid", body.user_id)
    await _audit(pool, admin, "expert.add", body.user_id, {"role": before["role"]}, {"role": "agronomist"}, request)
    row = await pool.fetchrow(_EXPERT_SELECT + " WHERE u.id = $1::uuid", body.user_id)
    return _expert_out(row)


@router.delete("/experts/{user_id}")
async def remove_expert(
    user_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    before = await pool.fetchrow("SELECT role FROM users WHERE id = $1::uuid", user_id)
    if not before:
        raise HTTPException(status_code=404, detail="User not found")
    await pool.execute("UPDATE users SET role = 'farmer', updated_at = NOW() WHERE id = $1::uuid", user_id)
    await _audit(pool, admin, "expert.remove", user_id, {"role": before["role"]}, {"role": "farmer"}, request)
    return {"ok": True}


@router.post("/experts/{user_id}/assign", response_model=ExpertProfileOut)
async def assign_expert(
    user_id: str,
    body: AssignExpertBody,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    user = await pool.fetchrow("SELECT id FROM users WHERE id = $1::uuid AND deleted_at IS NULL", user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await pool.execute(
        """
        INSERT INTO expert_assignments (user_id, crops, regions, updated_at)
        VALUES ($1::uuid, $2, $3, NOW())
        ON CONFLICT (user_id) DO UPDATE
            SET crops = EXCLUDED.crops, regions = EXCLUDED.regions, updated_at = NOW()
        """,
        user_id, body.crops, body.regions,
    )
    await _audit(pool, admin, "expert.assign", user_id, None,
                 {"crops": body.crops, "regions": body.regions}, request)
    row = await pool.fetchrow(_EXPERT_SELECT + " WHERE u.id = $1::uuid", user_id)
    return _expert_out(row)


# Notifications

@router.post("/notifications", response_model=NotificationResult)
async def send_notification(
    body: NotificationBody,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    if body.audience == "all":
        recipients = await pool.fetchval("SELECT count(*) FROM users WHERE deleted_at IS NULL AND is_active")
    elif body.audience == "experts":
        recipients = await pool.fetchval(
            "SELECT count(*) FROM users WHERE role = 'agronomist' AND deleted_at IS NULL"
        )
    else:  # group
        recipients = await pool.fetchval(
            "SELECT count(*) FROM users WHERE role = $1 AND deleted_at IS NULL", body.group or "farmer"
        )
    sent = int(recipients or 0)
    await pool.execute(
        """
        INSERT INTO notifications (title, body, audience, group_role, sent_count, created_by)
        VALUES ($1, $2, $3, $4, $5, $6::uuid)
        """,
        body.title, body.body, body.audience, body.group, sent, admin.get("sub"),
    )
    await _audit(pool, admin, "notification.send", None, None,
                 {"audience": body.audience, "title": body.title, "recipients": sent}, request)
    # NOTE: this records + counts recipients. Actual delivery (WebSocket/FCM/email)
    # is a separate channel — TODO(backend).
    return NotificationResult(sent=sent)


# User growth analytics (PostgreSQL-derived)

@router.get("/analytics/user-growth", response_model=list[UserGrowthPoint])
async def user_growth(
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
    days: int = Query(30, ge=1, le=120),
):
    rows = await pool.fetch(
        """
        SELECT
            to_char(gs, 'YYYY-MM-DD') AS date,
            (SELECT count(*) FROM users u WHERE u.created_at::date = gs::date) AS new_users,
            (SELECT count(*) FROM users u WHERE u.last_login_at::date = gs::date) AS active_users,
            (SELECT count(*) FROM users u
                WHERE u.last_login_at::date = gs::date AND u.created_at::date < gs::date) AS returning_users
        FROM generate_series(
            now()::date - ($1::int - 1) * interval '1 day',
            now()::date,
            interval '1 day'
        ) AS gs
        ORDER BY gs
        """,
        days,
    )
    return [
        UserGrowthPoint(
            date=r["date"],
            new_users=int(r["new_users"]),
            active_users=int(r["active_users"]),
            returning_users=int(r["returning_users"]),
        )
        for r in rows
    ]


# Model / Retrain

_MLFLOW_URL    = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
_VISION_AI_URL = os.getenv("VISION_AI_URL", "http://vision-ai:8001")
_AIRFLOW_URL   = os.getenv("AIRFLOW_URL", "http://airflow:8080")
_AIRFLOW_USER  = os.getenv("AIRFLOW_USERNAME", "admin")
_AIRFLOW_PASS  = os.getenv("AIRFLOW_PASSWORD", "")
_EXPERIMENT    = os.getenv("MLFLOW_EXPERIMENT", "plant-disease-classification")
_RETRAIN_DAG   = "retrain_classifier"


def _http(method: str, url: str, body: Optional[dict] = None,
          headers: Optional[dict] = None, timeout: int = 20) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else {}


async def _http_async(*args, **kwargs) -> dict:
    return await asyncio.to_thread(_http, *args, **kwargs)


@router.get("/models/runs")
async def model_runs(admin: dict = Depends(require_admin)):
    """Latest MLflow run per model with its key metrics (read-only)."""
    try:
        exp = await _http_async(
            "GET",
            f"{_MLFLOW_URL}/api/2.0/mlflow/experiments/get-by-name?experiment_name={_EXPERIMENT}",
        )
        exp_id = exp["experiment"]["experiment_id"]
        res = await _http_async(
            "POST", f"{_MLFLOW_URL}/api/2.0/mlflow/runs/search",
            {"experiment_ids": [exp_id], "max_results": 200,
             "order_by": ["attributes.start_time DESC"]},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"MLflow không phản hồi: {exc}")

    latest: dict[str, ModelRun] = {}
    for run in res.get("runs", []):
        data = run.get("data", {})
        tags = {t["key"]: t["value"] for t in data.get("tags", [])}
        name = tags.get("model_name")
        if not name or name in latest:
            continue
        metrics = {m["key"]: m["value"] for m in data.get("metrics", [])}
        info = run.get("info", {})
        latest[name] = ModelRun(
            model=name,
            run_id=info.get("run_id"),
            start_time=info.get("start_time"),
            test_macro_f1=metrics.get("test_macro_f1"),
            test_acc=metrics.get("test_acc"),
            val_acc=metrics.get("val_acc"),
        )
    return {"runs": list(latest.values())}


@router.post("/models/reload")
async def reload_serving_model(
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Hot-swap: pull the latest promoted weights into vision-ai and reload."""
    try:
        res = await _http_async(
            "POST", f"{_VISION_AI_URL}/admin/reload-model?sync=true", {}, timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Vision-AI không phản hồi: {exc}")
    await _audit(pool, admin, "model.reload", None, None, res, request)
    return res


@router.post("/retrain")
async def trigger_retrain(
    body: RetrainBody,
    request: Request,
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Trigger the Airflow retrain DAG (optionally for one model)."""
    conf = {"model": body.model} if body.model else {}
    url = f"{_AIRFLOW_URL}/api/v1/dags/{_RETRAIN_DAG}/dagRuns"
    auth = base64.b64encode(f"{_AIRFLOW_USER}:{_AIRFLOW_PASS}".encode()).decode()
    try:
        res = await _http_async(
            "POST", url, {"conf": conf},
            headers={"Authorization": f"Basic {auth}"}, timeout=30,
        )
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(
                status_code=502,
                detail="Airflow yêu cầu xác thực. Đặt AIRFLOW_USERNAME/PASSWORD cho auth service, "
                       "hoặc trigger trực tiếp trên Airflow UI (http://localhost:8090).",
            )
        raise HTTPException(status_code=502, detail=f"Airflow lỗi {exc.code}")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Airflow không phản hồi: {exc}")
    await _audit(pool, admin, "model.retrain_trigger", None, None, {"model": body.model}, request)
    return {"dag_run_id": res.get("dag_run_id"), "state": res.get("state")}


# Kafka monitoring (via kafka_exporter metrics in Prometheus)

_PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
_KAFKA_UI_URL   = os.getenv("KAFKA_UI_URL", "http://localhost:8080")


async def _promql(query: str) -> list[dict]:
    """Run an instant PromQL query; return the result vector ([] on any failure)."""
    url = f"{_PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(query)}"
    res = await _http_async("GET", url, timeout=10)
    if res.get("status") != "success":
        return []
    return res.get("data", {}).get("result", [])


def _sample_value(sample: dict) -> float:
    try:
        return float(sample["value"][1])
    except (KeyError, IndexError, ValueError, TypeError):
        return 0.0


@router.get("/kafka")
async def kafka_overview(admin: dict = Depends(require_admin)):
    """Kafka health from the kafka_exporter metrics scraped by Prometheus:
    broker count, topics (partitions + message count) and per-group consumer lag.
    Read-only; the heavy lifting (browse messages) lives in Kafka UI."""
    try:
        brokers_v  = await _promql("kafka_brokers")
        up_v       = await _promql('up{job="kafka"}')
        parts_v    = await _promql("sum(kafka_topic_partitions) by (topic)")
        offsets_v  = await _promql("sum(kafka_topic_partition_current_offset) by (topic)")
        lag_v      = await _promql("sum(kafka_consumergroup_lag) by (consumergroup, topic)")
        groupoff_v = await _promql("sum(kafka_consumergroup_current_offset) by (consumergroup, topic)")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Prometheus không phản hồi: {exc}")

    exporter_up = bool(up_v) and _sample_value(up_v[0]) >= 1
    brokers = int(_sample_value(brokers_v[0])) if brokers_v else 0

    # Topics: partition count + total messages (sum of end offsets). Skip internal __* topics.
    offsets_by_topic = {s["metric"].get("topic"): _sample_value(s) for s in offsets_v}
    topics = []
    for s in parts_v:
        t = s["metric"].get("topic", "")
        if t.startswith("__"):
            continue
        topics.append({
            "topic": t,
            "partitions": int(_sample_value(s)),
            "messages": int(offsets_by_topic.get(t, 0)),
        })
    topics.sort(key=lambda x: x["topic"])

    # Consumer groups: lag + committed offset per (group, topic).
    committed = {
        (s["metric"].get("consumergroup"), s["metric"].get("topic")): _sample_value(s)
        for s in groupoff_v
    }
    groups = []
    for s in lag_v:
        g = s["metric"].get("consumergroup", "")
        t = s["metric"].get("topic", "")
        if t.startswith("__"):
            continue
        groups.append({
            "group": g,
            "topic": t,
            "lag": int(_sample_value(s)),
            "committed_offset": int(committed.get((g, t), 0)),
        })
    groups.sort(key=lambda x: (x["group"], x["topic"]))

    return {
        "exporter_up": exporter_up,
        "brokers": brokers,
        "topics": topics,
        "consumer_groups": groups,
        "kafka_ui_url": _KAFKA_UI_URL,
    }


# GPU monitoring (via nvidia_gpu_exporter metrics in Prometheus)

@router.get("/gpu")
async def gpu_overview(admin: dict = Depends(require_admin)):
    """GPU stats from nvidia_gpu_exporter scraped by Prometheus: utilization, VRAM,
    temperature, power — per GPU. Read-only. `available=false` when no GPU exporter."""
    try:
        up_v   = await _promql('up{job="gpu"}')
        util_v = await _promql("nvidia_smi_utilization_gpu_ratio")
        memu_v = await _promql("nvidia_smi_memory_used_bytes")
        memt_v = await _promql("nvidia_smi_memory_total_bytes")
        temp_v = await _promql("nvidia_smi_temperature_gpu")
        powr_v = await _promql("nvidia_smi_power_draw_watts")
        info_v = await _promql("nvidia_smi_gpu_info")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Prometheus không phản hồi: {exc}")

    exporter_up = bool(up_v) and _sample_value(up_v[0]) >= 1
    names = {s["metric"].get("uuid"): s["metric"].get("name", "GPU") for s in info_v}

    def _by_uuid(vec: list[dict]) -> dict:
        return {s["metric"].get("uuid"): _sample_value(s) for s in vec}

    util, memu, memt, temp, powr = (_by_uuid(v) for v in (util_v, memu_v, memt_v, temp_v, powr_v))
    uuids = set(util) | set(memu) | set(memt) | set(temp) | set(powr)

    gpus = [
        {
            "uuid": u,
            "name": names.get(u, "GPU"),
            "util_pct": round(util.get(u, 0.0) * 100, 1),
            "mem_used_bytes": int(memu.get(u, 0)),
            "mem_total_bytes": int(memt.get(u, 0)),
            "temp_c": int(temp.get(u, 0)),
            "power_w": round(powr.get(u, 0.0), 1),
        }
        for u in sorted(uuids)
    ]
    return {"available": exporter_up and bool(gpus), "gpus": gpus}


# Reports (CSV export — real data from Postgres, stdlib only)

_REPORT_SQL: dict[str, str] = {
    "user": """
        SELECT username,
               COALESCE(full_name, '')  AS full_name,
               COALESCE(email, '')      AS email,
               COALESCE(phone, '')      AS phone,
               role,
               CASE WHEN is_active THEN 'active' ELSE 'locked' END AS status,
               to_char(last_login_at, 'YYYY-MM-DD HH24:MI')        AS last_login,
               to_char(created_at, 'YYYY-MM-DD')                   AS created_at
        FROM users
        WHERE deleted_at IS NULL
        ORDER BY created_at DESC
    """,
    "expert": """
        SELECT u.username,
               COALESCE(u.full_name, '') AS full_name,
               COALESCE(u.email, '')     AS email,
               COALESCE(array_to_string(ea.crops, '|'), '')   AS crops,
               COALESCE(array_to_string(ea.regions, '|'), '') AS regions,
               (SELECT count(*) FROM feedback f WHERE f.assignee_id = u.id AND f.status <> 'answered') AS active_cases,
               (SELECT count(*) FROM feedback f WHERE f.assignee_id = u.id AND f.status =  'answered') AS answered_cases
        FROM users u
        LEFT JOIN expert_assignments ea ON ea.user_id = u.id
        WHERE u.role = 'agronomist' AND u.deleted_at IS NULL
        ORDER BY u.username
    """,
    "feedback": """
        SELECT to_char(f.created_at, 'YYYY-MM-DD HH24:MI') AS created_at,
               COALESCE(u.username, '')        AS username,
               f.predicted_disease,
               f.confirmed_label,
               CASE WHEN f.is_correct THEN 'dung' ELSE 'sai' END AS is_correct,
               COALESCE(f.corrected_disease, '') AS corrected_disease,
               f.status
        FROM feedback f
        LEFT JOIN users u ON u.id = f.user_id
        ORDER BY f.created_at DESC
        LIMIT 5000
    """,
    "disease_trend": """
        SELECT confirmed_label AS disease,
               count(*)                                                            AS total,
               count(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days')      AS last_7_days,
               count(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days')     AS last_30_days
        FROM feedback
        GROUP BY confirmed_label
        ORDER BY total DESC
    """,
    "ai_performance": """
        SELECT predicted_disease,
               count(*)                                                              AS total,
               count(*) FILTER (WHERE is_correct)                                     AS correct,
               round(100.0 * count(*) FILTER (WHERE is_correct) / NULLIF(count(*), 0), 1) AS accuracy_pct,
               round(avg(predicted_confidence)::numeric, 3)                          AS avg_confidence
        FROM feedback
        GROUP BY predicted_disease
        ORDER BY total DESC
    """,
}


@router.get("/reports/{report_type}")
async def export_report(
    report_type: str,
    request: Request,
    format: str = Query("csv"),
    admin: dict = Depends(require_admin),
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Stream a report as CSV (UTF-8 BOM so Excel renders Vietnamese correctly).
    `format=excel` returns the same CSV — Excel opens it natively. Real data from
    Postgres; no extra dependencies."""
    sql = _REPORT_SQL.get(report_type)
    if sql is None:
        raise HTTPException(status_code=404, detail=f"Loại báo cáo không hợp lệ: {report_type}")

    rows = await pool.fetch(sql)
    header = list(rows[0].keys()) if rows else _REPORT_FALLBACK_HEADER.get(report_type, ["empty"])

    buf = io.StringIO()
    buf.write("﻿")  # BOM → Excel reads UTF-8 (Vietnamese) correctly
    writer = csv.writer(buf)
    writer.writerow(header)
    for r in rows:
        writer.writerow(["" if v is None else v for v in r.values()])
    buf.seek(0)

    await _audit(pool, admin, "report.export", report_type, None, {"format": format, "rows": len(rows)}, request)

    filename = f"{report_type}_report.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_REPORT_FALLBACK_HEADER: dict[str, list[str]] = {
    "user": ["username", "full_name", "email", "phone", "role", "status", "last_login", "created_at"],
    "expert": ["username", "full_name", "email", "crops", "regions", "active_cases", "answered_cases"],
    "feedback": ["created_at", "username", "predicted_disease", "confirmed_label", "is_correct", "corrected_disease", "status"],
    "disease_trend": ["disease", "total", "last_7_days", "last_30_days"],
    "ai_performance": ["predicted_disease", "total", "correct", "accuracy_pct", "avg_confidence"],
}
