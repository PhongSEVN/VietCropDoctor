from typing import Optional
from pydantic import BaseModel, field_validator, EmailStr


class RegisterRequest(BaseModel):
    """Public self-registration. Always creates a 'farmer' account — there is
    no client-settable role here on purpose. Granting 'agronomist' or 'admin'
    goes through the admin-only routes in routes/admin.py (create_user /
    update_user / expert.add), which are gated by require_admin."""

    username: str
    password: str
    email: Optional[str] = None

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 50:
            raise ValueError("username must be 3–50 characters")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("username may only contain letters, digits, _ and -")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class RegisterResponse(BaseModel):
    user_id: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    user_id: str
    username: str
    email: Optional[str]
    phone: Optional[str]
    role: str
    is_active: bool
    avatar_url: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def phone_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v and not v.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            raise ValueError("phone must contain only digits, +, - or spaces")
        if len(v) > 20:
            raise ValueError("phone must be at most 20 characters")
        return v or None


class SetCookieRequest(BaseModel):
    access_token: str
    refresh_token: str
