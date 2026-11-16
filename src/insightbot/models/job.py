"""Domain models for background worker jobs, leases, and fencing tokens."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class JobStatus(str, Enum):
    """Lifecycle states of a background job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED_DISABLED = "skipped_disabled"


class Job(BaseModel):
    """Background task record with bounded lease ownership and fencing token."""

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str  # e.g., 'ingest_source', 'extract_article', 'reconcile_versions'
    target_id: str  # source_id or article_id
    status: JobStatus = JobStatus.PENDING

    lease_owner: Optional[str] = None
    lease_expires_at: Optional[datetime] = None
    fencing_token: int = Field(default=1, ge=1)

    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    payload: dict[str, Any] = Field(default_factory=dict)
    result_data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    @field_validator("created_at", "updated_at", "lease_expires_at", mode="after")
    @classmethod
    def ensure_utc_job(cls, v: Optional[datetime]) -> Optional[datetime]:
        return _ensure_utc(v)
