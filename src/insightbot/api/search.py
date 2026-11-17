"""API endpoints for Lexical, Vector, and Hybrid Search."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from insightbot.api.deps import (
    get_search_service,
    require_analyst,
    require_viewer,
)
from insightbot.models.search import (
    SearchGeneration,
    SearchMode,
    SearchResponse,
)
from insightbot.models.user import User
from insightbot.modules.search.service import SearchService

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def execute_search(
    q: str = Query(..., min_length=1, max_length=512, description="Search terms or semantic query"),
    mode: SearchMode = Query(SearchMode.AUTO, description="Search mode: auto, hybrid, lexical, basic"),
    source_id: str | None = Query(None, description="Filter by publisher source ID"),
    language: str | None = Query(None, description="Filter by language code (ar, en, ru)"),
    start_date: datetime | None = Query(None, description="Earliest publication date (UTC)"),
    end_date: datetime | None = Query(None, description="Latest publication date (UTC)"),
    limit: int = Query(20, ge=1, le=100, description="Page result limit"),
    cursor: str | None = Query(None, description="Deterministic pagination cursor"),
    current_user: User = Depends(require_viewer),
    search_service: SearchService = Depends(get_search_service),
) -> SearchResponse:
    """
    Execute multilingual Hybrid search with Reciprocal Rank Fusion (RRF).
    Guarantees strict projection (no full body_text) and graceful Basic fallback.
    """
    return search_service.search(
        query=q,
        mode=mode,
        source_id=source_id,
        language=language,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        cursor=cursor,
    )


@router.post("/rebuild", response_model=SearchGeneration)
def rebuild_search_index(
    current_user: User = Depends(require_analyst),
    search_service: SearchService = Depends(get_search_service),
) -> SearchGeneration:
    """
    Trigger rebuild of an immutable search index generation with atomic alias swap.
    Restricted to Analyst or Admin roles.
    """
    try:
        gen = search_service.gen_manager.build_generation()
        return gen
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rebuild search index: {e}",
        )


@router.get("/status", response_model=dict[str, Any])
def get_search_status(
    current_user: User = Depends(require_viewer),
    search_service: SearchService = Depends(get_search_service),
) -> dict[str, Any]:
    """Retrieve active search generation metadata, vector dimensions, and index lag."""
    active_gen = search_service.gen_manager.get_active_generation()
    lag = search_service.gen_manager.calculate_index_lag_seconds()
    return {
        "has_active_generation": active_gen is not None,
        "active_generation": active_gen.model_dump() if active_gen else None,
        "index_lag_seconds": lag,
        "supported_modes": ["auto", "hybrid", "lexical", "basic"],
    }
