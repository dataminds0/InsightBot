"""Domain models for Data Exports, Formats, and Manifests."""

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class ExportFormat(str, Enum):
    """Allowed export formats."""

    CSV = "csv"
    JSONL = "jsonl"
    MARKDOWN = "markdown"


class ExportTarget(str, Enum):
    """Target entity collection for export."""

    ARTICLES = "articles"
    STORIES = "stories"


class ExportManifest(BaseModel):
    """Immutable manifest accompanying bounded export files."""

    export_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    target: ExportTarget
    format: ExportFormat
    total_exported: int
    generated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime = Field(
        default_factory=lambda: utc_now() + timedelta(hours=24)
    )
    filters_applied: dict[str, Any] = Field(default_factory=dict)
    formula_protection_applied: bool = True
    source_policy_enforced: bool = True
