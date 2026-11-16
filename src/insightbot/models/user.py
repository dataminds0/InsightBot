"""User, authorization, and session domain models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class Role(str, Enum):
    """User access control roles."""

    VIEWER = "viewer"
    ANALYST = "analyst"
    ADMIN = "admin"
    WORKER = "worker"


class UserStatus(str, Enum):
    """Account activation status."""

    ACTIVE = "active"
    PENDING = "pending"
    DISABLED = "disabled"


class User(BaseModel):
    """User account entity."""

    user_id: str = Field(default_factory=lambda: str(uuid4()))
    username: str
    email: Optional[str] = None
    password_hash: str
    role: Role = Role.VIEWER
    status: UserStatus = UserStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = None

    @field_validator("created_at", "updated_at", "last_login_at", mode="after")
    @classmethod
    def ensure_utc_user(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return None
        return _ensure_utc(v)


class Session(BaseModel):
    """Authenticated user session."""

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    session_token: str
    role: Role
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    last_activity_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at", "expires_at", "last_activity_at", mode="after")
    @classmethod
    def ensure_utc_session(cls, v: datetime) -> datetime:
        return _ensure_utc(v)
