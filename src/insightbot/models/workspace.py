"""Personal workspace models: Bookmarks, Saved Queries, and Private Notes."""

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class Bookmark(BaseModel):
    """Personal article bookmark."""

    bookmark_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    article_id: str
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class BookmarkItem(BaseModel):
    """Bookmark representation with target article summary and availability."""

    bookmark_id: str
    user_id: str
    article_id: str
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    target_available: bool = True
    article: dict[str, Any] | None = None


class BookmarkCreateRequest(BaseModel):
    """Request payload to create a bookmark."""

    article_id: str
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class SavedQuery(BaseModel):
    """Personal saved search query and filter parameters."""

    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str = Field(..., min_length=1, max_length=120)
    query_params: dict[str, Any] = Field(default_factory=dict)
    alerts_enabled: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SavedQueryCreateRequest(BaseModel):
    """Request payload to create a saved query."""

    name: str = Field(..., min_length=1, max_length=120)
    query_params: dict[str, Any] = Field(default_factory=dict)
    alerts_enabled: bool = False


class PrivateNote(BaseModel):
    """Personal analytical note on an article."""

    note_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    article_id: str
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class NoteItem(BaseModel):
    """Note representation with target article summary and availability."""

    note_id: str
    user_id: str
    article_id: str
    content: str
    created_at: datetime
    updated_at: datetime
    target_available: bool = True
    article: dict[str, Any] | None = None


class NoteUpdateRequest(BaseModel):
    """Request payload to create or update an article note."""

    content: str
