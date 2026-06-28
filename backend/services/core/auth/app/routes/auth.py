"""
Authentication routes: register, login, refresh, me, validate, set-cookie.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, UploadFile, File, status
from fastapi.responses import JSONResponse

import asyncpg
from redis.asyncio import Redis

from vcd_shared.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
    get_current_user,
)
from app.config import get_settings
from app.database import get_pool
from app.minio_client import AVATAR_BUCKET, upload_avatar
from app.models import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    SetCookieRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserProfile,
)

logger = logging.getLogger("auth.routes")
router = APIRouter(prefix="/auth", tags=["auth"])

_ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/jpg", "image/webp"}


def _avatar_url(avatar_path: str | None) -> str | None:
    if not avatar_path:
        return None
    settings = get_settings()
    return f"{settings.minio_public_url}/{AVATAR_BUCKET}/{avatar_path}"

_COOKIE_MAX_AGE_ACCESS  = get_settings().access_token_expire_minutes * 60
_COOKIE_MAX_AGE_REFRESH = get_settings().refresh_token_expire_days * 86400


# Redis helper

def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _refresh_key(user_id: str, token_tail: str) -> str:
    return f"refresh:{user_id}:{token_tail}"


# Endpoints


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, pool: asyncpg.Pool = Depends(get_pool)):
    existing = await pool.fetchrow("SELECT id FROM users WHERE username = $1", body.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    row = await pool.fetchrow(
        """
        INSERT INTO users (username, email, password_hash, role)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        body.username,
        body.email,
        hash_password(body.password),
        body.role,
    )
    return RegisterResponse(user_id=str(row["id"]))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, pool: asyncpg.Pool = Depends(get_pool)):
    row = await pool.fetchrow(
        "SELECT id, password_hash, role, is_active FROM users WHERE username = $1",
        body.username,
    )
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # Track last login for admin DAU/WAU/MAU analytics (best-effort).
    await pool.execute("UPDATE users SET last_login_at = NOW() WHERE id = $1", row["id"])

    user_id = str(row["id"])
    token_data = {"sub": user_id, "username": body.username, "role": row["role"]}

    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # Persist refresh token in Redis with TTL
    settings = get_settings()
    r = _redis()
    try:
        await r.setex(
            _refresh_key(user_id, refresh_token[-16:]),
            settings.refresh_token_expire_days * 86400,
            refresh_token,
        )
    finally:
        await r.aclose()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest):
    payload = verify_token(body.refresh_token, token_type="refresh")
    user_id = payload["sub"]

    r = _redis()
    try:
        stored = await r.get(_refresh_key(user_id, body.refresh_token[-16:]))
        if stored != body.refresh_token:
            raise HTTPException(status_code=401, detail="Refresh token revoked or invalid")

        # Rotate: delete old, issue new
        await r.delete(_refresh_key(user_id, body.refresh_token[-16:]))
        token_data = {k: payload[k] for k in ("sub", "username", "role") if k in payload}
        new_access  = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data)

        settings = get_settings()
        await r.setex(
            _refresh_key(user_id, new_refresh[-16:]),
            settings.refresh_token_expire_days * 86400,
            new_refresh,
        )
    finally:
        await r.aclose()

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.get("/me", response_model=UserProfile)
async def me(
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    row = await pool.fetchrow(
        "SELECT id, username, email, phone, role, is_active, avatar_path FROM users WHERE id = $1",
        user["sub"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserProfile(
        user_id=str(row["id"]),
        username=row["username"],
        email=row["email"],
        phone=row["phone"],
        role=row["role"],
        is_active=row["is_active"],
        avatar_url=_avatar_url(row["avatar_path"]),
    )


@router.patch("/me", response_model=UserProfile)
async def update_me(
    body: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    updates: list[str] = []
    values: list = []

    if body.email is not None:
        values.append(body.email)
        updates.append(f"email = ${len(values)}")
    if body.phone is not None:
        values.append(body.phone)
        updates.append(f"phone = ${len(values)}")

    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    values.append(user["sub"])
    sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ${len(values)} RETURNING id, username, email, phone, role, is_active, avatar_path"
    row = await pool.fetchrow(sql, *values)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfile(
        user_id=str(row["id"]),
        username=row["username"],
        email=row["email"],
        phone=row["phone"],
        role=row["role"],
        is_active=row["is_active"],
        avatar_url=_avatar_url(row["avatar_path"]),
    )


@router.post("/me/avatar", response_model=UserProfile)
async def upload_avatar_endpoint(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    pool: asyncpg.Pool = Depends(get_pool),
):
    if file.content_type not in _ALLOWED_AVATAR_TYPES:
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ ảnh JPEG, PNG, hoặc WebP")
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Ảnh đại diện không được vượt quá 5 MB")

    user_id = user["sub"]
    try:
        object_name = await upload_avatar(contents, user_id, file.content_type or "image/jpeg")
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    row = await pool.fetchrow(
        "UPDATE users SET avatar_path = $1 WHERE id = $2 RETURNING id, username, email, phone, role, is_active, avatar_path",
        object_name,
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfile(
        user_id=str(row["id"]),
        username=row["username"],
        email=row["email"],
        phone=row["phone"],
        role=row["role"],
        is_active=row["is_active"],
        avatar_url=_avatar_url(row["avatar_path"]),
    )


@router.post("/set-cookie")
async def set_cookie(body: SetCookieRequest, response: Response):
    """Store access + refresh tokens as httpOnly cookies.

    Called by the frontend immediately after /auth/login.
    """
    # Verify both tokens before setting cookies
    verify_token(body.access_token, token_type="access")
    verify_token(body.refresh_token, token_type="refresh")

    response.set_cookie(
        key="access_token",
        value=body.access_token,
        max_age=_COOKIE_MAX_AGE_ACCESS,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=body.refresh_token,
        max_age=_COOKIE_MAX_AGE_REFRESH,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/auth/refresh",
    )
    return {"status": "cookies set"}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    """Revoke refresh token and clear cookies."""
    r = _redis()
    try:
        # Revoke all refresh tokens for this user (scan by prefix)
        pattern = _refresh_key(user["sub"], "*")
        async for key in r.scan_iter(pattern):
            await r.delete(key)
    finally:
        await r.aclose()

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"status": "logged out"}


# WebSocket token echo (frontend → WS query param)

@router.get("/ws-token")
async def ws_token(request: Request):
    """Return the access_token from the httpOnly cookie as JSON.

    The frontend calls this with credentials:'include' so the cookie is sent,
    then passes the returned token as ?token= when upgrading to WebSocket.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    verify_token(token, token_type="access")
    return {"token": token}


# Nginx auth_request validation endpoints (internal use)


@router.get("/_validate")
async def validate_any(authorization: Optional[str] = Header(None)):
    """Return 200 + user headers for any authenticated request.

    Used as Nginx auth_request target for /predict and /query.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.removeprefix("Bearer ").strip()
    payload = verify_token(token)
    return JSONResponse(
        content={"ok": True},
        headers={
            "X-User-Id":   payload["sub"],
            "X-User-Role": payload.get("role", "farmer"),
            "X-Username":  payload.get("username", ""),
        },
    )


@router.get("/_validate/admin")
async def validate_admin(authorization: Optional[str] = Header(None)):
    """Return 200 only when the token carries the 'admin' role."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.removeprefix("Bearer ").strip()
    payload = verify_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return JSONResponse(
        content={"ok": True},
        headers={
            "X-User-Id":   payload["sub"],
            "X-User-Role": payload.get("role"),
        },
    )


@router.get("/_validate/agronomist")
async def validate_agronomist(authorization: Optional[str] = Header(None)):
    """Return 200 for agronomist or admin roles."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization.removeprefix("Bearer ").strip()
    payload = verify_token(token)
    if payload.get("role") not in ("agronomist", "admin"):
        raise HTTPException(status_code=403, detail="Agronomist or admin role required")
    return JSONResponse(
        content={"ok": True},
        headers={
            "X-User-Id":   payload["sub"],
            "X-User-Role": payload.get("role"),
        },
    )
