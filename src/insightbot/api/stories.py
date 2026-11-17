"""API endpoints for Story clusters, Event timelines, and Audited Merges/Splits."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from insightbot.api.deps import (
    get_story_service,
    require_analyst,
    require_viewer,
)
from insightbot.models.story import (
    Story,
    StoryAudit,
    StoryStatus,
)
from insightbot.models.user import User
from insightbot.modules.stories.service import StoryService

router = APIRouter(prefix="/api/stories", tags=["stories"])


class StoryListResponse(BaseModel):
    """Paginated list of stories."""

    items: list[dict[str, Any]]
    total: int
    next_cursor: str | None = None


class MergeStoriesRequest(BaseModel):
    """Payload for merging two stories."""

    target_story_id: str = Field(..., description="Story to merge into and retain")
    source_story_id: str = Field(..., description="Story being merged and closed")
    reason: str = Field(..., min_length=3, description="Justification for manual merger")


class SplitStoryRequest(BaseModel):
    """Payload for splitting articles from a story into a new story."""

    article_ids: list[str] = Field(..., min_length=1, description="Article IDs to move to new story")
    new_title: str = Field(..., min_length=3, description="Title for the newly created story")
    reason: str = Field(..., min_length=3, description="Justification for manual split")


@router.get("", response_model=StoryListResponse)
def list_stories(
    status_filter: StoryStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    current_user: User = Depends(require_viewer),
    story_service: StoryService = Depends(get_story_service),
) -> StoryListResponse:
    """List stories with deterministic cursor pagination and short projection (Defect A12)."""
    items, next_cursor, total = story_service.list_stories(
        status=status_filter, limit=limit, cursor=cursor
    )
    return StoryListResponse(items=items, total=total, next_cursor=next_cursor)


@router.get("/{story_id}", response_model=dict[str, Any])
def get_story(
    story_id: str,
    current_user: User = Depends(require_viewer),
    story_service: StoryService = Depends(get_story_service),
) -> dict[str, Any]:
    """Retrieve story detail with timeline member articles (excludes full body_text)."""
    story_data = story_service.get_story_detail(story_id)
    if not story_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story '{story_id}' was not found.",
        )
    return story_data


@router.post("/merge", response_model=Story)
def merge_stories(
    payload: MergeStoriesRequest,
    current_user: User = Depends(require_analyst),
    story_service: StoryService = Depends(get_story_service),
) -> Story:
    """Audited manual merge of source_story into target_story."""
    try:
        return story_service.merge_stories(
            target_story_id=payload.target_story_id,
            source_story_id=payload.source_story_id,
            actor_id=current_user.user_id,
            reason=payload.reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{story_id}/split", response_model=dict[str, Any])
def split_story(
    story_id: str,
    payload: SplitStoryRequest,
    current_user: User = Depends(require_analyst),
    story_service: StoryService = Depends(get_story_service),
) -> dict[str, Any]:
    """Audited manual split of articles from a story into a new story."""
    try:
        updated_source, new_story = story_service.split_story(
            source_story_id=story_id,
            article_ids_to_split=payload.article_ids,
            new_title=payload.new_title,
            actor_id=current_user.user_id,
            reason=payload.reason,
        )
        return {
            "source_story": updated_source.model_dump(),
            "new_story": new_story.model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{story_id}/history", response_model=list[StoryAudit])
def get_story_history(
    story_id: str,
    current_user: User = Depends(require_viewer),
    story_service: StoryService = Depends(get_story_service),
) -> list[StoryAudit]:
    """Retrieve chronological audit history for a story cluster."""
    story = story_service.get_story_detail(story_id)
    if not story:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Story '{story_id}' was not found.",
        )
    return story_service.get_story_history(story_id)
