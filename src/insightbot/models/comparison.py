"""Domain data models for Event Comparison across Sources, Timelines, and Attributed Divergences."""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from insightbot.models.story import StoryStatus


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class DivergenceCategory(str, Enum):
    """Categorization of attributed differences between sources."""

    NUMERICAL_FACTS = "numerical_facts"  # تباين في الأرقام والإحصاءات (مثلاً: 12 مقابل 45 ضحية)
    NAMED_ENTITIES = "named_entities"  # تباين في نسبة المسؤولية أو أسماء الفاعلين
    FRAMING_LANGUAGE = "framing_language"  # تباين في صياغة العنوان والمصطلحات المستخدمة
    TIMELINE_LATENCY = "timeline_latency"  # تباين في توقيت الحدث أو أسبقية النشر


class TimelineMilestone(BaseModel):
    """A single chronological milestone in an event timeline."""

    milestone_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime | None = None
    timestamp_basis: str = Field(
        default="published_at",
        description="Either 'published_at', 'fetched_at', or 'unknown' (Defect A13)",
    )
    source_id: str
    article_id: str
    version: int = 1
    title: str
    language: str
    lead_quote: str = Field(default="", description="Safe snippet <= 150 chars (Defect A12)")
    is_lead_article: bool = False


class SourcePerspective(BaseModel):
    """How a specific publisher framed and covered the event."""

    source_id: str
    article_count: int = 1
    first_reported_at: datetime | None = None
    first_reported_basis: str = "published_at"
    latest_reported_at: datetime | None = None
    headline: str
    lead_article_id: str
    lead_article_version: int = 1
    key_entities: list[str] = Field(default_factory=list)
    framing_terms: list[str] = Field(default_factory=list)
    numerical_claims: list[str] = Field(default_factory=list)
    word_count: int = 0
    reading_time_minutes: int = 1
    latency_minutes_from_first: int = 0


class AttributedDifference(BaseModel):
    """A concrete, verifiable divergence in claims between two publishers."""

    difference_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: DivergenceCategory
    description: str
    source_a: str
    source_a_claim: str
    source_a_citation: str  # Format: "article_id:v{version}"
    source_b: str
    source_b_claim: str
    source_b_citation: str  # Format: "article_id:v{version}"
    severity: str = "medium"  # "high", "medium", "low"


class VersionedEvidence(BaseModel):
    """Concrete immutable quote tied to an exact article ID and version."""

    evidence_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    article_id: str
    version: int
    source_id: str
    canonical_url: str
    exact_quote: str
    published_at: datetime | None = None
    context_title: str


class AnalystReview(BaseModel):
    """Audited Analyst/Admin review of story coverage comparison and membership."""

    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    story_id: str
    reviewer_id: str
    status: str = "verified"  # "verified", "flagged", "in_dispute"
    notes: str
    excluded_article_ids: list[str] = Field(default_factory=list)
    reviewed_at: datetime = Field(default_factory=utc_now)


class EventComparisonReport(BaseModel):
    """Comprehensive comparison report across sources for an event/story cluster."""

    story_id: str
    story_title: str
    story_status: StoryStatus
    created_at: datetime
    sources_count: int
    articles_count: int
    timeline: list[TimelineMilestone] = Field(default_factory=list)
    perspectives: list[SourcePerspective] = Field(default_factory=list)
    divergent_points: list[AttributedDifference] = Field(default_factory=list)
    evidence_items: list[VersionedEvidence] = Field(default_factory=list)
    latest_review: AnalystReview | None = None
    first_reported_source: str | None = None
    reporting_span_hours: float = 0.0


class ReviewStoryRequest(BaseModel):
    """Request payload for Analyst/Admin review of a story."""

    status: str = Field(default="verified", description="'verified', 'flagged', or 'in_dispute'")
    notes: str = Field(..., min_length=3, description="Analyst review justification")
    excluded_article_ids: list[str] = Field(
        default_factory=list, description="Optional article IDs to exclude from this story"
    )
