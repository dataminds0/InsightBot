"""Notifications API endpoints for in-app alerts, read status, and alert toggling."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from insightbot.api.deps import (
    get_alert_service,
    get_notification_repository,
    require_analyst,
    require_viewer,
)
from insightbot.models.notifications import (
    AlertToggleRequest,
    InAppNotification,
    NotificationSummary,
)
from insightbot.models.user import User
from insightbot.models.workspace import SavedQuery
from insightbot.modules.alerts.service import AlertService
from insightbot.repositories.notification_repository import NotificationRepository

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationSummary)
def list_notifications(
    is_read: bool | None = Query(None, description="Filter by read status"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(require_viewer),
    repo: NotificationRepository = Depends(get_notification_repository),
) -> NotificationSummary:
    """List in-app notifications for the authenticated user."""
    items = repo.list_notifications(
        user_id=current_user.user_id,
        is_read=is_read,
        limit=limit,
        skip=skip,
    )
    total = repo.count_total(user_id=current_user.user_id, is_read=is_read)
    unread_count = repo.count_unread(user_id=current_user.user_id)
    return NotificationSummary(items=items, total=total, unread_count=unread_count)


@router.get("/unread-count")
def get_unread_count(
    current_user: User = Depends(require_viewer),
    repo: NotificationRepository = Depends(get_notification_repository),
) -> dict[str, int]:
    """Get the unread notification count for the current user."""
    count = repo.count_unread(user_id=current_user.user_id)
    return {"unread_count": count}


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(require_viewer),
    repo: NotificationRepository = Depends(get_notification_repository),
) -> dict[str, Any]:
    """Mark a specific notification as read."""
    success = repo.mark_as_read(user_id=current_user.user_id, notification_id=notification_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    return {"status": "success", "notification_id": notification_id}


@router.post("/read-all")
def mark_all_notifications_read(
    current_user: User = Depends(require_viewer),
    repo: NotificationRepository = Depends(get_notification_repository),
) -> dict[str, Any]:
    """Mark all unread notifications for the user as read."""
    modified_count = repo.mark_all_as_read(user_id=current_user.user_id)
    return {"status": "success", "marked_read_count": modified_count}


@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    current_user: User = Depends(require_viewer),
    repo: NotificationRepository = Depends(get_notification_repository),
) -> dict[str, Any]:
    """Delete a notification."""
    success = repo.delete_notification(user_id=current_user.user_id, notification_id=notification_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        )
    return {"status": "success", "notification_id": notification_id}


@router.post("/alerts/toggle", response_model=SavedQuery)
def toggle_query_alert(
    payload: AlertToggleRequest,
    current_user: User = Depends(require_analyst),
    service: AlertService = Depends(get_alert_service),
) -> SavedQuery:
    """Configure alert delivery, pause state, and cooldown for a saved query."""
    updated = service.configure_saved_query_alert(user_id=current_user.user_id, request=payload)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Saved query not found.",
        )
    return updated


@router.post("/alerts/evaluate", response_model=list[InAppNotification])
def evaluate_alerts(
    article_id: str | None = Query(None, description="Optional article ID to evaluate"),
    current_user: User = Depends(require_analyst),
    service: AlertService = Depends(get_alert_service),
) -> list[InAppNotification]:
    """Trigger alert evaluation against articles (supports replay tests and worker runs)."""
    if article_id:
        doc = service.articles_col.find_one({"article_id": article_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Article {article_id} not found.",
            )
        return service.evaluate_article_alerts(doc)

    # Evaluate last 50 articles
    articles = list(service.articles_col.find().sort("fetched_at", -1).limit(50))
    all_notifs: list[InAppNotification] = []
    for art in articles:
        all_notifs.extend(service.evaluate_article_alerts(art))
    return all_notifs
