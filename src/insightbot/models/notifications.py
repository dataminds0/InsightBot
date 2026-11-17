"""In-app notifications and alert configuration models."""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class InAppNotification(BaseModel):
    """In-app notification for analysts and administrators."""

    notification_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=2000)
    notification_type: str = Field(
        ...,
        description="Type: saved_query_match, story_update, briefing_ready, system_alert",
    )
    target_type: str = Field(..., description="Target: article, story, saved_query")
    target_id: str
    target_version: int | None = None
    is_read: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class NotificationSummary(BaseModel):
    """Paginated list of notifications with unread count."""

    items: list[InAppNotification]
    total: int
    unread_count: int


class AlertToggleRequest(BaseModel):
    """Request payload to toggle or update alert configuration for a saved query."""

    query_id: str
    alerts_enabled: bool
    is_paused: bool = False
    cooldown_hours: int = Field(default=1, ge=1, le=168)
