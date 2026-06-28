"""
Expert review router — the backend for the agronomist dashboard.

Mounted at /expert (the gateway exposes it as /api/expert/* behind
auth_request /auth-validate-agronomist). Operates on the shared `feedback` table
(+ expert_responses, internal_notes) which the auth service migrates.

Closing the loop: when an expert answers with a corrected diagnosis, the verified
image is copied into the gold bucket (feedback_minio.copy_to_verified) so the R2
build_training_set.py job folds the human label into the next retrain.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from jose import JWTError, jwt
from pydantic import BaseModel

from app import database as db
from app import feedback_minio

logger = logging.getLogger("rag_engine.expert")
router = APIRouter(prefix="/expert", tags=["expert"])

_JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-use-64-char-random")
_JWT_ALGORITHM = "HS256"
_STATUSES = ("pending", "in_progress", "answered")
_PRIORITIES = ("low", "normal", "high", "urgent")

# Sentinel question marker for the synthetic chat_messages row that surfaces an
# expert reply inside the farmer's original conversation. The web client renders
# rows carrying this marker as a single "expert" bubble (see ChatPage.tsx).
_EXPERT_REPLY_MARKER = "__EXPERT_REPLY__"


# RBAC

def require_expert(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
) -> dict:
    """Resolve the acting expert. Trusts gateway-injected headers; falls back to
    decoding the JWT for direct (non-gateway) calls. Requires agronomist/admin."""
    uid, role = x_user_id, x_user_role
    if (not uid or not role) and authorization and authorization.startswith("Bearer "):
        try:
            payload = jwt.decode(authorization.removeprefix("Bearer ").strip(),
                                 _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
            uid = uid or str(payload.get("sub", ""))
            role = role or payload.get("role")
        except JWTError:
            pass
    if role not in ("agronomist", "admin"):
        raise HTTPException(status_code=403, detail="Agronomist or admin role required")
    if not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"id": uid, "role": role}


async def _pool():
    pool = await db._get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return pool


# Models (mirror client/web/src/types/expert.ts)

class AiAnalysis(BaseModel):
    predicted_disease: str
    predicted_confidence: float
    top3: Optional[list] = None
    agreement_score: Optional[float] = None
    model_count: Optional[int] = None


class ExpertResponseEntry(BaseModel):
    id: str
    expert_id: Optional[str] = None
    expert_name: Optional[str] = None
    comment: str
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    attachment_urls: list[str] = []
    created_at: str


class InternalNote(BaseModel):
    id: str
    expert_id: Optional[str] = None
    expert_name: Optional[str] = None
    note: str
    created_at: str


class ExpertCase(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    image_url: Optional[str] = None
    related_image_urls: Optional[list[str]] = None
    crop: Optional[str] = None
    problem_description: Optional[str] = None
    status: str
    priority: str
    is_irrelevant: bool = False
    created_at: str
    updated_at: Optional[str] = None
    ai: AiAnalysis
    current_diagnosis: Optional[str] = None
    responses: list[ExpertResponseEntry] = []
    notes: list[InternalNote] = []
    conversation: Optional[list] = None
    sla_due_at: Optional[str] = None


class ExpertResponseInput(BaseModel):
    comment: str
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    attachment_urls: list[str] = []
    mark_completed: bool = False


class StatusPatch(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None


class NoteBody(BaseModel):
    note: str


class AssignBody(BaseModel):
    expert_id: str


class IrrelevantBody(BaseModel):
    irrelevant: bool = True


class OnlineExpert(BaseModel):
    id: str
    name: str
    active_cases: int
    online: bool = False


class DiagnosisItem(BaseModel):
    """A single image diagnosis from chat_messages — includes diagnoses the user
    never gave feedback on. `feedback_id` is set only once a feedback/case row exists."""
    chat_id: str
    user_id: str
    user_name: Optional[str] = None
    image_url: Optional[str] = None
    disease: Optional[str] = None          # AI-predicted disease
    created_at: str
    has_feedback: bool = False
    feedback_id: Optional[str] = None
    status: str = "new"                    # "new" when no feedback row yet
    is_irrelevant: bool = False


# Mappers

def _iso(dt: Any) -> Optional[str]:
    return dt.isoformat() if dt else None


def _case_row(r, responses: list, notes: list) -> ExpertCase:
    return ExpertCase(
        id=str(r["id"]),
        user_id=str(r["user_id"]),
        user_name=(r["full_name"] or r["username"]) if r["username"] else None,
        image_url=r["image_url"],
        problem_description=r["comment"],
        status=r["status"],
        priority=r["priority"],
        is_irrelevant=bool(r["is_irrelevant"]),
        created_at=r["created_at"].isoformat(),
        updated_at=_iso(r["updated_at"]),
        ai=AiAnalysis(
            predicted_disease=r["predicted_disease"],
            predicted_confidence=float(r["predicted_confidence"]),
        ),
        current_diagnosis=r["confirmed_label"],
        responses=responses,
        notes=notes,
        sla_due_at=_iso(r["sla_due_at"]),
    )


_CASE_SELECT = """
    SELECT f.*, u.username, u.full_name
    FROM feedback f LEFT JOIN users u ON u.id = f.user_id
"""


async def _responses(pool, case_id: str) -> list[ExpertResponseEntry]:
    rows = await pool.fetch(
        """
        SELECT er.*, u.username, u.full_name
        FROM expert_responses er LEFT JOIN users u ON u.id = er.expert_id
        WHERE er.feedback_id = $1::uuid ORDER BY er.created_at ASC
        """,
        case_id,
    )
    return [
        ExpertResponseEntry(
            id=str(r["id"]),
            expert_id=str(r["expert_id"]) if r["expert_id"] else None,
            expert_name=(r["full_name"] or r["username"]) if r["username"] else None,
            comment=r["comment"],
            diagnosis=r["diagnosis"],
            treatment=r["treatment"],
            attachment_urls=list(r["attachment_urls"] or []),
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


async def _notes(pool, case_id: str) -> list[InternalNote]:
    rows = await pool.fetch(
        """
        SELECT n.*, u.username, u.full_name
        FROM internal_notes n LEFT JOIN users u ON u.id = n.expert_id
        WHERE n.feedback_id = $1::uuid ORDER BY n.created_at ASC
        """,
        case_id,
    )
    return [
        InternalNote(
            id=str(r["id"]),
            expert_id=str(r["expert_id"]) if r["expert_id"] else None,
            expert_name=(r["full_name"] or r["username"]) if r["username"] else None,
            note=r["note"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]


def _build_farmer_message(body: ExpertResponseInput, expert_name: str) -> str:
    """Render an expert response as Vietnamese markdown for the farmer's chat bubble.

    The "expert" attribution badge is added by the web client, so this body only
    carries the substance (comment + confirmed diagnosis + treatment + attachments).
    """
    parts: list[str] = [body.comment.strip()]
    if body.diagnosis:
        parts.append(f"**Chẩn đoán xác nhận:** {body.diagnosis.strip()}")
    if body.treatment:
        parts.append(f"**Hướng xử lý đề xuất:** {body.treatment.strip()}")
    for url in body.attachment_urls:
        parts.append(f"[Tài liệu đính kèm]({url})")
    parts.append(f"— {expert_name}")
    return "\n\n".join(p for p in parts if p)


async def _push_reply_to_farmer_chat(pool, fb, body: ExpertResponseInput, expert_id: str) -> None:
    """Surface the expert reply inside the farmer's original conversation by writing
    a marker-tagged chat_messages row. No-op when the case has no chat session.

    Best-effort: a failure here must not fail the expert's submission, so it is
    logged and swallowed (the canonical record already lives in expert_responses).
    """
    if not fb["session_id"]:
        return
    try:
        expert_row = await pool.fetchrow(
            "SELECT full_name, username FROM users WHERE id = $1::uuid", expert_id
        )
        expert_name = "Chuyên gia"
        if expert_row:
            expert_name = expert_row["full_name"] or expert_row["username"] or expert_name
        answer = _build_farmer_message(body, expert_name)
        await pool.execute(
            """
            INSERT INTO chat_messages (user_id, session_id, disease, question, answer, image_url)
            VALUES ($1::uuid, $2, $3, $4, $5, NULL)
            """,
            str(fb["user_id"]), fb["session_id"], fb["confirmed_label"],
            _EXPERT_REPLY_MARKER, answer,
        )
    except Exception:
        logger.warning("Failed to push expert reply into farmer chat", exc_info=True)


async def _detail(pool, case_id: str) -> ExpertCase:
    row = await pool.fetchrow(_CASE_SELECT + " WHERE f.id = $1::uuid", case_id)
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return _case_row(row, await _responses(pool, case_id), await _notes(pool, case_id))


# Endpoints

@router.get("/cases", response_model=list[ExpertCase])
async def list_cases(expert: dict = Depends(require_expert), limit: int = Query(200, ge=1, le=500)):
    pool = await _pool()
    rows = await pool.fetch(_CASE_SELECT + " ORDER BY f.created_at DESC LIMIT $1", limit)
    return [_case_row(r, [], []) for r in rows]


@router.get("/diagnoses", response_model=list[DiagnosisItem])
async def list_diagnoses(
    expert: dict = Depends(require_expert),
    pending_only: bool = Query(False, description="Only diagnoses not yet answered by an expert"),
    limit: int = Query(300, ge=1, le=1000),
):
    """List EVERY image diagnosis (from chat_messages), including ones the user never
    gave feedback on. Each is matched to its feedback/case row (if any) via image_url
    so the expert can see review status and act on un-reviewed images."""
    pool = await _pool()
    rows = await pool.fetch(
        """
        SELECT cm.id AS chat_id, cm.user_id, cm.disease, cm.image_url, cm.created_at,
               u.username, u.full_name,
               f.id AS feedback_id, f.status AS f_status, f.is_irrelevant
        FROM chat_messages cm
        LEFT JOIN users u ON u.id = cm.user_id
        LEFT JOIN LATERAL (
            SELECT fb.id, fb.status, fb.is_irrelevant
            FROM feedback fb
            WHERE fb.image_url = cm.image_url
            ORDER BY fb.created_at DESC
            LIMIT 1
        ) f ON TRUE
        WHERE cm.image_url IS NOT NULL AND cm.disease IS NOT NULL
        ORDER BY cm.created_at DESC
        LIMIT $1
        """,
        limit,
    )
    items = [
        DiagnosisItem(
            chat_id=str(r["chat_id"]),
            user_id=str(r["user_id"]),
            user_name=(r["full_name"] or r["username"]) if r["username"] else None,
            image_url=r["image_url"],
            disease=r["disease"],
            created_at=r["created_at"].isoformat(),
            has_feedback=r["feedback_id"] is not None,
            feedback_id=str(r["feedback_id"]) if r["feedback_id"] else None,
            status=r["f_status"] or "new",
            is_irrelevant=bool(r["is_irrelevant"]),
        )
        for r in rows
    ]
    if pending_only:
        items = [it for it in items if it.status not in ("answered",)]
    return items


@router.post("/diagnoses/{chat_id}/promote", response_model=ExpertCase)
async def promote_diagnosis(chat_id: str, expert: dict = Depends(require_expert)):
    """Turn a feedback-less diagnosis into a reviewable case.

    Idempotent: if a feedback row already exists for the same image it is returned.
    Otherwise a synthetic feedback row is created from the chat_message so the standard
    response / verify / retrain flow (copy_to_verified) applies unchanged."""
    pool = await _pool()
    cm = await pool.fetchrow(
        "SELECT id, user_id, session_id, disease, image_url FROM chat_messages WHERE id = $1::uuid",
        chat_id,
    )
    if not cm:
        raise HTTPException(status_code=404, detail="Diagnosis not found")
    if not cm["image_url"]:
        raise HTTPException(status_code=422, detail="This message has no image to review")

    existing = await pool.fetchrow(
        "SELECT id FROM feedback WHERE image_url = $1 ORDER BY created_at DESC LIMIT 1",
        cm["image_url"],
    )
    if existing:
        return await _detail(pool, str(existing["id"]))

    label = cm["disease"] or "unknown"
    row = await pool.fetchrow(
        """
        INSERT INTO feedback (user_id, session_id, image_url, predicted_disease,
            predicted_confidence, is_correct, confirmed_label, comment, status, priority)
        VALUES ($1::uuid, $2, $3, $4, 0, true, $4, $5, 'pending', 'normal')
        RETURNING id
        """,
        str(cm["user_id"]), cm["session_id"], cm["image_url"], label,
        "(Chuyên gia chủ động xem xét — chưa có phản hồi người dùng)",
    )
    return await _detail(pool, str(row["id"]))


@router.get("/cases/{case_id}", response_model=ExpertCase)
async def get_case(case_id: str, expert: dict = Depends(require_expert)):
    return await _detail(await _pool(), case_id)


@router.post("/cases/{case_id}/responses", response_model=ExpertCase)
async def add_response(case_id: str, body: ExpertResponseInput, expert: dict = Depends(require_expert)):
    pool = await _pool()
    fb = await pool.fetchrow("SELECT * FROM feedback WHERE id = $1::uuid", case_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Case not found")

    await pool.execute(
        """
        INSERT INTO expert_responses (feedback_id, expert_id, comment, diagnosis, treatment, attachment_urls)
        VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)
        """,
        case_id, expert["id"], body.comment, body.diagnosis, body.treatment, body.attachment_urls,
    )

    new_status = "answered" if body.mark_completed else "in_progress"
    confirmed = body.diagnosis or fb["confirmed_label"]
    verified_path = fb["verified_image_path"]

    # Expert-corrected diagnosis → copy the image into the gold bucket so the
    # retrain loop (R2) learns from the human label.
    if body.diagnosis and fb["image_url"]:
        vp = await feedback_minio.copy_to_verified(fb["image_url"], body.diagnosis)
        if vp:
            verified_path = vp

    await pool.execute(
        """
        UPDATE feedback
        SET status = $2, confirmed_label = $3,
            corrected_disease = COALESCE($4, corrected_disease),
            verified_image_path = $5, updated_at = NOW()
        WHERE id = $1::uuid
        """,
        case_id, new_status, confirmed, body.diagnosis, verified_path,
    )

    # Close the loop back to the farmer: drop the reply into their original chat
    # so it shows up next time they open that conversation.
    fb_updated = dict(fb)
    fb_updated["confirmed_label"] = confirmed
    await _push_reply_to_farmer_chat(pool, fb_updated, body, expert["id"])

    return await _detail(pool, case_id)


@router.patch("/cases/{case_id}", response_model=ExpertCase)
async def patch_case(case_id: str, body: StatusPatch, expert: dict = Depends(require_expert)):
    pool = await _pool()
    sets, args = [], []
    if body.status is not None:
        if body.status not in _STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status")
        args.append(body.status); sets.append(f"status = ${len(args)}")
    if body.priority is not None:
        if body.priority not in _PRIORITIES:
            raise HTTPException(status_code=422, detail="Invalid priority")
        args.append(body.priority); sets.append(f"priority = ${len(args)}")
    if not sets:
        return await _detail(pool, case_id)
    args.append(case_id)
    row = await pool.fetchrow(
        f"UPDATE feedback SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${len(args)}::uuid RETURNING id",
        *args,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return await _detail(pool, case_id)


@router.post("/cases/{case_id}/notes", response_model=ExpertCase)
async def add_note(case_id: str, body: NoteBody, expert: dict = Depends(require_expert)):
    pool = await _pool()
    fb = await pool.fetchrow("SELECT id FROM feedback WHERE id = $1::uuid", case_id)
    if not fb:
        raise HTTPException(status_code=404, detail="Case not found")
    await pool.execute(
        "INSERT INTO internal_notes (feedback_id, expert_id, note) VALUES ($1::uuid, $2::uuid, $3)",
        case_id, expert["id"], body.note,
    )
    return await _detail(pool, case_id)


@router.post("/cases/{case_id}/assign", response_model=ExpertCase)
async def assign_case(case_id: str, body: AssignBody, expert: dict = Depends(require_expert)):
    pool = await _pool()
    row = await pool.fetchrow(
        "UPDATE feedback SET assignee_id = $2::uuid, updated_at = NOW() WHERE id = $1::uuid RETURNING id",
        case_id, body.expert_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return await _detail(pool, case_id)


@router.post("/cases/{case_id}/irrelevant", response_model=ExpertCase)
async def mark_irrelevant(case_id: str, body: IrrelevantBody, expert: dict = Depends(require_expert)):
    """Flag (or unflag) a case whose image is not a crop leaf (irrelevant / OOD).

    Marking irrelevant resolves the case (status='answered') and keeps it OUT of the
    verified/training set — it is never copied to the gold bucket because no expert
    diagnosis is submitted. Unmarking reopens it for review.
    """
    pool = await _pool()
    if body.irrelevant:
        row = await pool.fetchrow(
            "UPDATE feedback SET is_irrelevant = true, status = 'answered', updated_at = NOW() "
            "WHERE id = $1::uuid RETURNING id",
            case_id,
        )
    else:
        row = await pool.fetchrow(
            "UPDATE feedback SET is_irrelevant = false, status = 'in_progress', updated_at = NOW() "
            "WHERE id = $1::uuid RETURNING id",
            case_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return await _detail(pool, case_id)


@router.get("/online", response_model=list[OnlineExpert])
async def online_experts(expert: dict = Depends(require_expert)):
    pool = await _pool()
    rows = await pool.fetch(
        """
        SELECT u.id, u.username, u.full_name,
               (SELECT count(*) FROM feedback f
                WHERE f.assignee_id = u.id AND f.status <> 'answered') AS active_cases
        FROM users u
        WHERE u.role = 'agronomist' AND u.deleted_at IS NULL
        ORDER BY u.username
        """
    )
    return [
        OnlineExpert(
            id=str(r["id"]),
            name=r["full_name"] or r["username"],
            active_cases=int(r["active_cases"] or 0),
            online=False,  # TODO: real presence via WS/Redis heartbeat
        )
        for r in rows
    ]
