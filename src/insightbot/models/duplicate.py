"""Domain data models for article duplicate relationships and evidence tracking."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class DuplicateType(str, Enum):
    """Categorization of duplicate relationship."""

    EXACT_HASH = "exact_hash"  # Identical body text hash across different URLs/sources
    SYNDICATION = "syndication"  # Wire agency republishing (Reuters, AFP, etc.)
    NEAR_DUPLICATE = "near_duplicate"  # High text similarity (> 0.85) without conflicting facts


class DuplicateStatus(str, Enum):
    """Operational status of the duplicate relationship."""

    CONFIRMED = "confirmed"
    FLAGGED = "flagged"
    REJECTED = "rejected"


class DuplicateEvidence(BaseModel):
    """Technical evidence and similarity metrics explaining the relationship."""

    content_hash_match: bool = False
    jaccard_similarity: float = 0.0
    headline_similarity: float = 0.0
    shared_wire_agency: str | None = None
    differing_numbers_found: list[str] = Field(default_factory=list)
    temporal_delta_hours: float = 0.0
    reason: str = ""
    extra_data: dict[str, Any] = Field(default_factory=dict)


class DuplicateRelationship(BaseModel):
    """
    Immutable relationship between a canonical reference article and a duplicate copy.
    Preserves both publisher records while identifying redundant coverage.
    """

    relationship_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    canonical_article_id: str
    duplicate_article_id: str
    duplicate_type: DuplicateType
    status: DuplicateStatus = DuplicateStatus.CONFIRMED
    similarity_score: float = Field(ge=0.0, le=1.0)
    evidence: DuplicateEvidence = Field(default_factory=DuplicateEvidence)
    detected_at: datetime = Field(default_factory=utc_now)
