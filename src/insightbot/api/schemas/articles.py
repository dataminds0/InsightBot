"""API response and request schemas for articles and pagination."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ArticleListItem(BaseModel):
    """
    Projected summary of an article for listing and search.
    STRICT SECURITY & PERFORMANCE RULE:
    Does NOT contain 'body_text' to prevent whole-corpus memory exhaustion in lists.
    """

    article_id: str
    source_id: str
    canonical_url: str
    title: str
    language: str
    published_at: Optional[datetime] = None
    publication_date_unknown_reason: Optional[str] = None
    fetched_at: datetime
    current_version: int
    stage_states: dict[str, str] = Field(default_factory=dict)
    quarantine_reason: Optional[str] = None
    word_count: int = 0
    reading_time_minutes: int = 1


class ArticleDetail(BaseModel):
    """Complete article model including full original body text."""

    article_id: str
    source_id: str
    canonical_url: str
    original_url: str
    resolved_url: str
    title: str
    body_text: str  # Full original text included only in individual detail view
    content_hash: str
    language: str
    published_at: Optional[datetime] = None
    publication_date_unknown_reason: Optional[str] = None
    fetched_at: datetime
    first_seen_at: datetime
    updated_at: datetime
    current_version: int
    fencing_token: int
    stage_states: dict[str, str] = Field(default_factory=dict)
    quarantine_reason: Optional[str] = None
    word_count: int = 0
    reading_time_minutes: int = 1
    extra_metadata: dict[str, Any] = Field(default_factory=dict)


class ArticleVersionItem(BaseModel):
    """Snapshot of a specific article revision."""

    article_id: str
    version: int
    title: str
    body_text: str
    content_hash: str
    operation: str
    created_at: datetime
    raw_storage_key: Optional[str] = None


class ArticleListResponse(BaseModel):
    """Paginated article listing response with cursor token."""

    items: list[ArticleListItem]
    total_count: int
    limit: int
    next_cursor: Optional[str] = None
