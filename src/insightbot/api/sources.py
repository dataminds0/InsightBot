"""Sources API endpoints: list registered publishers and inspect source policies."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from insightbot.api.deps import get_source_repository, require_viewer
from insightbot.config import Settings, get_settings
from insightbot.models.source import Source
from insightbot.models.user import User
from insightbot.modules.sources.registry import load_sources_from_yaml, sync_sources_to_db
from insightbot.repositories.source_repository import SourceRepository

router = APIRouter(prefix="/api/sources", tags=["Sources"])


@router.get("", response_model=list[Source])
def list_sources(
    enabled_only: bool = Query(False, description="Filter for enabled sources only"),
    current_user: User = Depends(require_viewer),
    source_repo: SourceRepository = Depends(get_source_repository),
    settings: Settings = Depends(get_settings),
) -> list[Source]:
    """
    List all configured publisher sources.
    If database collection is not yet populated, initializes from sources.yaml automatically.
    """
    sources = source_repo.list_sources(enabled_only=enabled_only)
    if not sources and not enabled_only and settings.sources_config_path.exists():
        # First-time sync from validated configuration
        yaml_sources = load_sources_from_yaml(settings.sources_config_path)
        sync_sources_to_db(yaml_sources, source_repo)
        sources = source_repo.list_sources(enabled_only=enabled_only)
    return sources


@router.get("/{source_id}", response_model=Source)
def get_source_detail(
    source_id: str,
    current_user: User = Depends(require_viewer),
    source_repo: SourceRepository = Depends(get_source_repository),
) -> Source:
    """Fetch publisher source definition and operational policy."""
    source = source_repo.get_by_id(source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_id}' was not found.",
        )
    return source
