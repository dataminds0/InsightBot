"""Administrator source management and health inspection endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from insightbot.api.deps import get_audit_repository, get_source_repository, require_admin
from insightbot.models.source import Source
from insightbot.models.user import User
from insightbot.repositories.audit_repository import AuditRepository
from insightbot.repositories.source_repository import SourceRepository

router = APIRouter(prefix="/api/admin/sources", tags=["Admin Sources"])


class SourceHealthItem(BaseModel):
    source_id: str
    name: str
    url: str
    language: str
    enabled: bool
    rate_limit_per_minute: int
    retention_days: int
    total_articles: int
    latest_fetched_at: Optional[datetime] = None
    latest_published_at: Optional[datetime] = None
    failed_jobs_count: int = 0
    recent_error: Optional[str] = None


class ToggleSourceRequest(BaseModel):
    enabled: bool


@router.get("/health", response_model=list[SourceHealthItem])
def get_sources_health(
    admin: User = Depends(require_admin),
    source_repo: SourceRepository = Depends(get_source_repository),
) -> list[SourceHealthItem]:
    """Retrieve health, freshness, article counts, and failure reasons per source (Admin only)."""
    summary = source_repo.get_source_health_summary()
    return [SourceHealthItem.model_validate(item) for item in summary]


@router.patch("/{source_id}/toggle", response_model=Source)
def toggle_source(
    source_id: str,
    req: ToggleSourceRequest,
    admin: User = Depends(require_admin),
    source_repo: SourceRepository = Depends(get_source_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> Source:
    """Enable or disable a publisher source (Admin only)."""
    source = source_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' was not found.",
        )

    source_repo.set_enabled(source_id, req.enabled)
    audit_repo.record(
        actor_id=admin.user_id,
        action="toggle_source",
        entity_type="source",
        entity_id=source_id,
        details={"enabled": req.enabled, "previous": source.enabled},
    )

    updated = source_repo.get_by_id(source_id)
    assert updated is not None
    return updated
