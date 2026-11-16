"""Data models for extracted article content and metadata."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExtractedArticle(BaseModel):
    """Normalized article representation extracted from raw HTML."""

    title: str
    body_text: str
    published_at: Optional[datetime] = None
    publication_date_unknown_reason: Optional[str] = None
    author: Optional[str] = None
    language: str = "ar"
    quarantine_reason: Optional[str] = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
