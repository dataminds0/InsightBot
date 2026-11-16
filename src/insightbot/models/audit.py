"""Audit log domain models for system and administrative events."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditLog(BaseModel):
    """Immutable audit trail entry."""

    log_id: str = Field(default_factory=lambda: str(uuid4()))
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
