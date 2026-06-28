"""
JWT authentication utilities shared across all VietCropDoctor services.

Usage:
    from vcd_shared.auth import get_current_user, role_required

    @app.get("/protected")
    async def handler(user: dict = Depends(get_current_user)):
        ...

    @app.delete("/admin-only")
    async def admin_handler(user: dict = Depends(role_required("admin"))):
        ...
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

# Configuration


class JWTConfig:
    SECRET_KEY: str = os.getenv("JWT_SECRET", "change-me-in-production-use-64-char-random")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "52560000"))  # 100 years
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "36500"))          # 100 years


_cfg = JWTConfig()
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

VALID_ROLES = frozenset({"farmer", "agronomist", "admin"})
_ROLE_LEVEL = {"farmer": 0, "agronomist": 1, "admin": 2}

# Password helpers

def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# Token creation

def create_access_token(data: dict) -> str:
    payload = {
        **data,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_cfg.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, _cfg.SECRET_KEY, algorithm=_cfg.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = {
        **data,
        "exp": datetime.now(timezone.utc) + timedelta(days=_cfg.REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, _cfg.SECRET_KEY, algorithm=_cfg.ALGORITHM)


# Token verification


def verify_token(token: str, token_type: str = "access") -> dict:
    """Decode and validate a JWT.

    Raises:
        HTTPException 401 if the token is missing, expired, or invalid.
    """
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _cfg.SECRET_KEY, algorithms=[_cfg.ALGORITHM])
    except JWTError:
        raise exc
    if payload.get("type") != token_type:
        raise exc
    if "sub" not in payload:
        raise exc
    return payload


# FastAPI dependencies

async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> dict:
    """FastAPI dependency: return the authenticated user's token payload.

    Raises HTTPException 401 when the request carries no valid Bearer token.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_token(token)


def role_required(role: str):
    """FastAPI dependency factory: require a minimum role level.

    Roles in ascending order: farmer < agronomist < admin

    Example:
        @app.post("/ingest")
        async def ingest(user: dict = Depends(role_required("admin"))):
            ...
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Unknown role '{role}'. Valid roles: {VALID_ROLES}")

    required_level = _ROLE_LEVEL[role]

    async def _check(user: dict = Depends(get_current_user)) -> dict:
        user_level = _ROLE_LEVEL.get(user.get("role", "farmer"), 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' or higher is required",
            )
        return user

    return _check
