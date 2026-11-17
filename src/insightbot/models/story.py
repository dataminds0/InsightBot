"""Domain data models for Story Clusters, Events, Lifecycle, and Audited Merge/Split."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class StoryStatus(str, Enum):
    """Lifecycle stages of a story/event cluster."""

    EMERGING = "emerging"  # تشكّل / حدث عاجل أولي
    PEAK = "peak"  # ذروة التغطية وتعدد المصادر
    DECLINING = "declining"  # تراجع واستقرار التغطية
    CLOSED = "closed"  # مغلقة أو مكتملة


class StoryAuditAction(str, Enum):
    """Auditable operations performed on story clusters."""

    CREATED = "created"
    ARTICLE_ADDED = "article_added"
    ARTICLE_REMOVED = "article_removed"
    MERGED = "merged"
    SPLIT = "split"
    STATUS_CHANGED = "status_changed"
    MANUAL_EDIT = "manual_edit"


class EntityCategory(str, Enum):
    """Entity categorization."""

    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    GEOPOLITICAL = "geopolitical"


class EntityMention(BaseModel):
    """
    Extracted entity mention linked to specific article character offsets.
    Guarantees ambiguity is left unresolved rather than hallucinating links.
    """

    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    category: EntityCategory
    article_id: str
    start_char: int = 0
    end_char: int = 0
    resolved_id: str | None = None
    is_resolved: bool = False
    confidence: float = 1.0


class Story(BaseModel):
    """
    Story / Event cluster grouping articles covering the same real-world event over time.
    Maintains provenance, source diversity, temporal bounds, and optimistic versioning.
    """

    story_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    summary: str = ""
    status: StoryStatus = StoryStatus.EMERGING
    lead_article_id: str
    article_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    article_count: int = 1
    sources_count: int = 1
    first_article_at: datetime
    last_article_at: datetime
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    peak_at: datetime | None = None
    closed_at: datetime | None = None
    primary_location: str | None = None
    keywords: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    version: int = 1


class StorySnapshot(BaseModel):
    """Immutable snapshot of story state before/after major lifecycle mutations."""

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    story_id: str
    version: int
    story_data: dict[str, Any]
    captured_at: datetime = Field(default_factory=utc_now)


class StoryAudit(BaseModel):
    """Audit record for story mergers, splits, manual reassignments, and lifecycle changes."""

    audit_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    story_id: str
    action: StoryAuditAction
    actor_id: str  # user_id or 'system_worker'
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)
