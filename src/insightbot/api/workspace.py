"""Personal workspace router for bookmarks, saved queries, and analytical notes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from insightbot.api.deps import get_workspace_repository, require_analyst
from insightbot.models.user import User
from insightbot.models.workspace import (
    Bookmark,
    BookmarkCreateRequest,
    BookmarkItem,
    NoteItem,
    NoteUpdateRequest,
    PrivateNote,
    SavedQuery,
    SavedQueryCreateRequest,
)
from insightbot.repositories.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspace", tags=["Workspace"])


# --- Bookmarks ---


@router.get("/bookmarks", response_model=dict[str, Any])
def list_bookmarks(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    tag: str | None = Query(None),
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, Any]:
    """List bookmarked articles for the current analyst with target availability."""
    items, total = workspace_repo.list_bookmarks(
        user_id=current_user.user_id,
        skip=skip,
        limit=limit,
        tag=tag,
    )
    return {
        "items": [BookmarkItem.model_validate(it) for it in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/bookmarks", response_model=Bookmark, status_code=status.HTTP_201_CREATED)
def create_bookmark(
    payload: BookmarkCreateRequest,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> Bookmark:
    """Create or update a personal bookmark for an article."""
    return workspace_repo.add_bookmark(
        user_id=current_user.user_id,
        article_id=payload.article_id,
        notes=payload.notes,
        tags=payload.tags,
    )


@router.delete("/bookmarks/{article_id}", response_model=dict[str, Any])
def delete_bookmark(
    article_id: str,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, Any]:
    """Remove a bookmark for an article."""
    deleted = workspace_repo.remove_bookmark(
        user_id=current_user.user_id,
        article_id=article_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bookmark not found.",
        )
    return {"deleted": True, "article_id": article_id}


@router.get("/bookmarks/status/{article_id}", response_model=dict[str, Any])
def get_bookmark_status(
    article_id: str,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, Any]:
    """Check if the current analyst has bookmarked a specific article."""
    bookmark = workspace_repo.get_bookmark(
        user_id=current_user.user_id,
        article_id=article_id,
    )
    return {
        "is_bookmarked": bookmark is not None,
        "bookmark": bookmark,
    }


# --- Saved Queries ---


@router.get("/queries", response_model=dict[str, Any])
def list_saved_queries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, Any]:
    """List saved queries owned by the current analyst."""
    items, total = workspace_repo.list_queries(
        user_id=current_user.user_id,
        skip=skip,
        limit=limit,
    )
    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/queries", response_model=SavedQuery, status_code=status.HTTP_201_CREATED)
def create_saved_query(
    payload: SavedQueryCreateRequest,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> SavedQuery:
    """Save a search query and filter criteria."""
    # Alert delivery is disabled until T19
    alerts_flag = False
    if payload.alerts_enabled:
        logger.info(
            "Alert delivery requested for query '%s' but disabled until Task T19",
            payload.name,
        )

    return workspace_repo.save_query(
        user_id=current_user.user_id,
        name=payload.name,
        query_params=payload.query_params,
        alerts_enabled=alerts_flag,
    )


@router.get("/queries/{query_id}", response_model=SavedQuery)
def get_saved_query(
    query_id: str,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> SavedQuery:
    """Get a saved query ensuring strict owner isolation."""
    query = workspace_repo.get_query(
        user_id=current_user.user_id,
        query_id=query_id,
    )
    if not query:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved query not found or not accessible.",
        )
    return query


@router.delete("/queries/{query_id}", response_model=dict[str, Any])
def delete_saved_query(
    query_id: str,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, Any]:
    """Delete a saved query ensuring strict owner isolation."""
    deleted = workspace_repo.delete_query(
        user_id=current_user.user_id,
        query_id=query_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved query not found or not accessible.",
        )
    return {"deleted": True, "query_id": query_id}


# --- Private Notes ---


@router.get("/notes", response_model=dict[str, Any])
def list_notes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, Any]:
    """List private analytical notes with target article previews."""
    items, total = workspace_repo.list_notes(
        user_id=current_user.user_id,
        skip=skip,
        limit=limit,
    )
    return {
        "items": [NoteItem.model_validate(it) for it in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/notes/{article_id}", response_model=PrivateNote)
def get_article_note(
    article_id: str,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> PrivateNote:
    """Get private note on an article."""
    note = workspace_repo.get_note(
        user_id=current_user.user_id,
        article_id=article_id,
    )
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found for this article.",
        )
    return note


@router.put("/notes/{article_id}", response_model=PrivateNote)
def upsert_article_note(
    article_id: str,
    payload: NoteUpdateRequest,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> PrivateNote:
    """Create or update private analytical note on an article."""
    return workspace_repo.upsert_note(
        user_id=current_user.user_id,
        article_id=article_id,
        content=payload.content,
    )


@router.delete("/notes/{article_id}", response_model=dict[str, Any])
def delete_article_note(
    article_id: str,
    current_user: User = Depends(require_analyst),
    workspace_repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> dict[str, Any]:
    """Delete a private analytical note on an article."""
    deleted = workspace_repo.delete_note(
        user_id=current_user.user_id,
        article_id=article_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found for this article.",
        )
    return {"deleted": True, "article_id": article_id}
