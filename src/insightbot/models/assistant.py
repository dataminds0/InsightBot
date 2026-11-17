"""Analyst assistant models: asynchronous jobs, cancellation, and citation validation."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from insightbot.models.generation import GenerationOutput


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


AssistantJobStatus = Literal["pending", "processing", "completed", "cancelled", "failed"]


class AssistantJob(BaseModel):
    """Asynchronous assistant query execution job."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    query: str = Field(..., min_length=1, max_length=2000)
    story_id: str | None = None
    source_id: str | None = None
    max_passages: int = 6
    status: AssistantJobStatus = "pending"
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    deadline_at: datetime = Field(default_factory=utc_now)
    result: GenerationOutput | None = None
    error_message: str | None = None
    cancelled_by: str | None = None


class AssistantAskRequest(BaseModel):
    """Request payload to submit a question to the assistant."""

    query: str = Field(..., min_length=1, max_length=2000)
    story_id: str | None = None
    source_id: str | None = None
    max_passages: int = Field(default=6, ge=1, le=12)


class AssistantJobResponse(BaseModel):
    """Response containing assistant job details and queue positioning."""

    job: AssistantJob
    queue_position: int = 0
