"""Article API endpoints: projected listing, detail, and immutable revision snapshots."""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from insightbot.api.deps import (
    get_article_repository,
    get_deduplication_service,
    require_analyst,
    require_viewer,
)
from insightbot.api.schemas.articles import (
    ArticleDetail,
    ArticleListItem,
    ArticleListResponse,
    ArticleVersionItem,
)
from insightbot.models.user import User
from insightbot.modules.deduplication.service import DeduplicationService
from insightbot.repositories.article_repository import ArticleRepository

router = APIRouter(prefix="/api/articles", tags=["Articles"])


@router.get("", response_model=ArticleListResponse)
def list_articles(
    source_id: Optional[str] = Query(None, description="Filter by publisher source ID"),
    language: Optional[str] = Query(None, description="Filter by language (e.g. ar, en, ru)"),
    q: Optional[str] = Query(None, description="Search keyword in article titles"),
    start_date: Optional[datetime] = Query(None, description="Filter published_at >= start_date"),
    end_date: Optional[datetime] = Query(None, description="Filter published_at <= end_date"),
    include_unknown_date: bool = Query(
        True, description="Include articles where publication date is unknown"
    ),
    cursor: Optional[str] = Query(None, description="Deterministic cursor token for pagination"),
    limit: int = Query(
        20, ge=1, le=100, description="Page limit (max 100 to prevent corpus loading)"
    ),
    current_user: User = Depends(require_viewer),
    article_repo: ArticleRepository = Depends(get_article_repository),
) -> ArticleListResponse:
    """
    List articles with database-level projection.
    Strictly excludes 'body_text' to prevent whole-corpus memory exhaustion.
    Uses deterministic cursor pagination on (published_at, article_id).
    """
    items, total_count, next_cursor = article_repo.list_projected_articles(
        source_id=source_id,
        language=language,
        q=q,
        start_date=start_date,
        end_date=end_date,
        include_unknown_date=include_unknown_date,
        cursor=cursor,
        limit=limit,
    )

    list_items = [ArticleListItem.model_validate(item) for item in items]
    return ArticleListResponse(
        items=list_items,
        total_count=total_count,
        limit=limit,
        next_cursor=next_cursor,
    )


@router.get("/{article_id}", response_model=ArticleDetail)
def get_article_detail(
    article_id: str,
    current_user: User = Depends(require_viewer),
    article_repo: ArticleRepository = Depends(get_article_repository),
) -> ArticleDetail:
    """
    Fetch a single article in detail, including full original body text.
    Full body text is delivered exclusively in individual item view.
    """
    article = article_repo.get_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article '{article_id}' was not found.",
        )
    data = article.model_dump()
    wc = article.word_count or len(article.body_text.split())
    data["word_count"] = wc
    data["reading_time_minutes"] = max(1, (wc + 199) // 200) if wc > 0 else 1
    return ArticleDetail.model_validate(data)


@router.get("/{article_id}/versions", response_model=list[ArticleVersionItem])
def get_article_versions(
    article_id: str,
    current_user: User = Depends(require_viewer),
    article_repo: ArticleRepository = Depends(get_article_repository),
) -> list[ArticleVersionItem]:
    """Retrieve full audit revision history for an article."""
    article = article_repo.get_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article '{article_id}' was not found.",
        )

    revisions = article_repo.get_versions(article_id)
    return [ArticleVersionItem.model_validate(r.model_dump()) for r in revisions]


@router.get("/{article_id}/versions/{version_number}", response_model=ArticleVersionItem)
def get_article_version_snapshot(
    article_id: str,
    version_number: int,
    current_user: User = Depends(require_viewer),
    article_repo: ArticleRepository = Depends(get_article_repository),
) -> ArticleVersionItem:
    """Retrieve a specific immutable revision snapshot by version number."""
    revision = article_repo.get_version_by_number(article_id, version_number)
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_number} for article '{article_id}' was not found.",
        )
    return ArticleVersionItem.model_validate(revision.model_dump())


@router.get("/{article_id}/duplicates", response_model=list[dict[str, Any]])
def get_article_duplicates(
    article_id: str,
    current_user: User = Depends(require_viewer),
    article_repo: ArticleRepository = Depends(get_article_repository),
    dedup_service: DeduplicationService = Depends(get_deduplication_service),
) -> list[dict[str, Any]]:
    """Retrieve all confirmed duplicate and syndication relationships for an article."""
    article = article_repo.get_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article '{article_id}' was not found.",
        )
    return dedup_service.get_duplicates_for_article_with_previews(article_id)


@router.post("/{article_id}/deduplicate", response_model=list[dict[str, Any]])
def run_article_deduplication(
    article_id: str,
    current_user: User = Depends(require_analyst),
    article_repo: ArticleRepository = Depends(get_article_repository),
    dedup_service: DeduplicationService = Depends(get_deduplication_service),
) -> list[dict[str, Any]]:
    """Trigger deduplication check on an article against temporal candidate window."""
    article = article_repo.get_by_id(article_id)
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Article '{article_id}' was not found.",
        )
    dedup_service.deduplicate_article(article_id)
    return dedup_service.get_duplicates_for_article_with_previews(article_id)
