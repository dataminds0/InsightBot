"""Domain models for Analytics, Metric contracts, and Reporting."""

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class SourceCoverageMetric(BaseModel):
    """Coverage statistics for an approved news source."""

    source_id: str
    name: str = ""
    article_count: int = 0
    percentage: float = 0.0
    average_reading_time_minutes: float = 1.0
    average_word_count: float = 0.0
    latest_article_at: datetime | None = None
    publishing_lag_minutes: float | None = None  # Avg minutes between published_at and fetched_at


class LanguageDistributionMetric(BaseModel):
    """Language breakdown across collected articles."""

    language: str
    count: int = 0
    percentage: float = 0.0


class TimelinePoint(BaseModel):
    """Daily or hourly article volume milestone."""

    date: str  # YYYY-MM-DD
    count: int = 0
    sources_breakdown: dict[str, int] = Field(default_factory=dict)


class StoryStatusDistribution(BaseModel):
    """Distribution of stories across lifecycle stages."""

    status: str
    count: int = 0
    percentage: float = 0.0


class AnalyticsOverviewReport(BaseModel):
    """Comprehensive analytics overview report reconciling underlying data."""

    total_articles: int = 0
    total_sources: int = 0
    total_stories: int = 0
    unknown_publication_date_count: int = 0  # Defect A13 visible metric
    quarantined_articles_count: int = 0  # Defect A05/A06 visible metric
    source_coverage: list[SourceCoverageMetric] = Field(default_factory=list)
    language_distribution: list[LanguageDistributionMetric] = Field(default_factory=list)
    timeline_trend: list[TimelinePoint] = Field(default_factory=list)
    story_status_distribution: list[StoryStatusDistribution] = Field(default_factory=list)
    as_of: datetime = Field(default_factory=utc_now)
