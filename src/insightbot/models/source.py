"""Domain data models for publisher news sources."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class SourcePolicy(BaseModel):
    """Operational policies for a publisher source."""

    rate_limit_per_minute: int = Field(default=30, ge=1)
    retention_days: int = Field(default=90, ge=1)
    allow_raw_storage: bool = True
    owner: str = "system"


class Source(BaseModel):
    """Publisher source registry definition."""

    source_id: str
    name: str
    url: str
    feed_urls: list[str] = Field(default_factory=list)
    language: str = "ar"
    enabled: bool = False
    policy: SourcePolicy = Field(default_factory=SourcePolicy)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extra_config: dict[str, Any] = Field(default_factory=dict)
