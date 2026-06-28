"""Pydantic schemas for the admin router (user management, audit, KPIs)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, field_validator

BackendRole = Literal["farmer", "agronomist", "admin"]
UserStatus = Literal["active", "locked", "deleted"]


class AdminUserOut(BaseModel):
    id: str
    username: str
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    role: BackendRole
    status: UserStatus
    created_at: str
    last_login_at: Optional[str] = None


class PaginatedUsers(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int


class CreateUserBody(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None
    role: BackendRole = "farmer"

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 50:
            raise ValueError("username must be 3–50 characters")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("username may only contain letters, digits, _ and -")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class UpdateUserBody(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[BackendRole] = None


class AuditLogOut(BaseModel):
    id: str
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    action: str
    target: Optional[str] = None
    timestamp: str
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    before: Optional[Any] = None
    after: Optional[Any] = None


class PaginatedAudit(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int


class AuditCreateBody(BaseModel):
    action: str
    target: Optional[str] = None
    before: Optional[Any] = None
    after: Optional[Any] = None


class AdminKpisOut(BaseModel):
    total_users: int
    new_today: int
    new_week: int
    new_month: int
    dau: int
    wau: int
    mau: int
    retention_rate: Optional[float] = None
    churn_rate: Optional[float] = None
    total_feedback: int
    total_images: int
    total_ai_analyses: int
    total_expert_responses: int


# Experts

class ExpertProfileOut(BaseModel):
    id: str
    name: str
    online: bool = False
    handled_cases: int = 0
    completion_rate: float = 0.0
    avg_response_minutes: Optional[float] = None
    rating: Optional[float] = None
    crops: list[str] = []
    regions: list[str] = []


class AddExpertBody(BaseModel):
    user_id: str


class AssignExpertBody(BaseModel):
    crops: list[str] = []
    regions: list[str] = []


# Notifications

class NotificationBody(BaseModel):
    title: str
    body: str
    audience: Literal["all", "experts", "group"]
    group: Optional[str] = None


class NotificationResult(BaseModel):
    sent: int


# Analytics

class UserGrowthPoint(BaseModel):
    date: str
    new_users: int
    active_users: int
    returning_users: int


# Model / Retrain

class RetrainBody(BaseModel):
    """Optional single-model selection; empty = all 5 models."""
    model: Optional[str] = None


class ModelRun(BaseModel):
    model: str
    run_id: Optional[str] = None
    start_time: Optional[int] = None
    test_macro_f1: Optional[float] = None
    test_acc: Optional[float] = None
    val_acc: Optional[float] = None
