"""Domain data models for articles and versioned content."""

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def compute_content_hash(text: str) -> str:
    """Compute deterministic SHA-256 hash of normalized text."""
    normalized = " ".join(text.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ArticleRevision(BaseModel):
    """Immutable snapshot of article content at a specific version."""

    article_id: str
    version: int = Field(ge=1)
    title: str
    body_text: str
    content_hash: str
    operation: str = "initial_fetch"  # e.g., 'initial_fetch', 're-extraction', 'correction'
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_storage_key: Optional[str] = None


class Article(BaseModel):
    """Canonical article representation with version tracking and provenance."""

    article_id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    canonical_url: str
    original_url: str
    resolved_url: str
    title: str
    body_text: str
    content_hash: str
    language: str = "ar"  # 'ar', 'en', 'ru'

    published_at: Optional[datetime] = None
    publication_date_unknown_reason: Optional[str] = None

    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    current_version: int = Field(default=1, ge=1)
    fencing_token: int = Field(default=1, ge=1)
    word_count: int = 0

    @property
    def reading_time_minutes(self) -> int:
        """Estimated reading time based on word count (Defect A14)."""
        wc = self.word_count or len(self.body_text.split())
        return max(1, (wc + 199) // 200) if wc > 0 else 1

    stage_states: dict[str, str] = Field(
        default_factory=lambda: {
            "fetch": "completed",
            "extraction": "completed",
            "deduplication": "pending",
            "classification": "pending",
            "summarization": "pending",
        }
    )
    quarantine_reason: Optional[str] = None
    extra_metadata: dict[str, Any] = Field(default_factory=dict)
