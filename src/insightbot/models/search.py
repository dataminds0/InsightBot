"""Domain data models for Lexical, Vector, and Hybrid Search."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class SearchMode(str, Enum):
    """Operational mode of the search engine."""

    AUTO = "auto"
    HYBRID = "hybrid"
    LEXICAL = "lexical"
    BASIC = "basic"
    BASIC_FALLBACK = "basic_fallback"


class SearchResultItem(BaseModel):
    """
    Search result item with relevance scores and strict short projection.
    Strictly omits full body_text to defend against memory exhaustion (Defect A12).
    """

    article_id: str
    source_id: str
    canonical_url: str
    title: str
    language: str
    published_at: datetime | None = None
    fetched_at: datetime
    word_count: int = 0
    reading_time_minutes: int = 1
    score: float = 0.0
    lexical_rank: int | None = None
    vector_rank: int | None = None
    rrf_score: float | None = None
    snippet: str = ""


class SearchResponse(BaseModel):
    """Paginated search response with provenance, generation identifier, and index lag."""

    items: list[SearchResultItem]
    total: int
    search_mode: SearchMode
    index_generation: str
    index_lag_seconds: float = 0.0
    fallback_reason: str | None = None
    query: str
    as_of: datetime = Field(default_factory=utc_now)
    next_cursor: str | None = None


class SearchGeneration(BaseModel):
    """Metadata for an immutable search index generation with atomic alias swap."""

    generation_id: str = Field(default_factory=lambda: f"gen_{uuid.uuid4().hex[:12]}")
    is_active: bool = False
    article_count: int = 0
    chunks_count: int = 0
    vector_dimensions: int = 384
    created_at: datetime = Field(default_factory=utc_now)
    activated_at: datetime | None = None
    status: str = "valid"  # building, valid, stale
    metadata: dict[str, Any] = Field(default_factory=dict)
