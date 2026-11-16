"""Data models for HTTP fetch audit logs and crawl frontier."""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class FetchRecord(BaseModel):
    """Immutable audit record of an HTTP fetch attempt."""

    fetch_id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    url: str
    status_code: int
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    response_time_ms: int = 0
    content_hash: Optional[str] = None
    raw_storage_key: Optional[str] = None
    error: Optional[str] = None
