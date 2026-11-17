"""Repository for managing in-app notifications and dedup replay defenses."""

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from insightbot.models.notifications import InAppNotification

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class NotificationRepository:
    """Handles persistence, read states, and replay-proof deduplication of in-app notifications."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.notifications = db["in_app_notifications"]
        self.dedup = db["notification_dedup_records"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create required indexes for query performance and replay idempotency."""
        try:
            self.notifications.create_index([("user_id", 1), ("created_at", -1)])
            self.notifications.create_index([("user_id", 1), ("is_read", 1)])
            self.dedup.create_index(
                [("user_id", 1), ("query_id", 1), ("target_id", 1)],
                unique=True,
            )
        except Exception as exc:
            logger.warning("NotificationRepository index creation notice: %s", exc)

    def create_notification(self, notification: InAppNotification) -> InAppNotification:
        """Persist a new in-app notification."""
        doc = notification.model_dump()
        self.notifications.insert_one(doc)
        return notification

    def list_notifications(
        self,
        user_id: str,
        is_read: bool | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> list[InAppNotification]:
        """List notifications for a user ordered newest first."""
        query: dict[str, Any] = {"user_id": user_id}
        if is_read is not None:
            query["is_read"] = is_read

        cursor = (
            self.notifications.find(query, {"_id": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        return [InAppNotification.model_validate(doc) for doc in cursor]

    def count_unread(self, user_id: str) -> int:
        """Count unread notifications for a user."""
        return self.notifications.count_documents({"user_id": user_id, "is_read": False})

    def count_total(self, user_id: str, is_read: bool | None = None) -> int:
        """Count total notifications matching filter."""
        query: dict[str, Any] = {"user_id": user_id}
        if is_read is not None:
            query["is_read"] = is_read
        return self.notifications.count_documents(query)

    def mark_as_read(self, user_id: str, notification_id: str) -> bool:
        """Mark a specific notification as read."""
        res = self.notifications.update_one(
            {"user_id": user_id, "notification_id": notification_id},
            {"$set": {"is_read": True}},
        )
        return res.modified_count > 0

    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all unread notifications for a user as read."""
        res = self.notifications.update_many(
            {"user_id": user_id, "is_read": False},
            {"$set": {"is_read": True}},
        )
        return res.modified_count

    def delete_notification(self, user_id: str, notification_id: str) -> bool:
        """Delete a notification by ID."""
        res = self.notifications.delete_one(
            {"user_id": user_id, "notification_id": notification_id}
        )
        return res.deleted_count > 0

    def is_already_notified(self, user_id: str, query_id: str, target_id: str) -> bool:
        """Check if an alert was already generated for this user, query, and target."""
        doc = self.dedup.find_one(
            {"user_id": user_id, "query_id": query_id, "target_id": target_id}
        )
        return doc is not None

    def record_notification_dedup(self, user_id: str, query_id: str, target_id: str) -> bool:
        """Atomically record deduplication key. Returns False if already recorded (replay defense)."""
        try:
            self.dedup.insert_one(
                {
                    "user_id": user_id,
                    "query_id": query_id,
                    "target_id": target_id,
                    "created_at": utc_now(),
                }
            )
            return True
        except DuplicateKeyError:
            return False
