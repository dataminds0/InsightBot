"""Alert service evaluating saved queries with cooldown, pause, and replay idempotency."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.notifications import AlertToggleRequest, InAppNotification
from insightbot.models.workspace import SavedQuery
from insightbot.repositories.notification_repository import NotificationRepository

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class AlertService:
    """Evaluates incoming news events and articles against users' active saved queries."""

    def __init__(self, db: Database[dict[str, Any]], notification_repo: NotificationRepository):
        self.db = db
        self.notification_repo = notification_repo
        self.saved_queries_col = db["saved_queries"]
        self.articles_col = db["articles"]
        self.stories_col = db["stories"]

    def configure_saved_query_alert(
        self, user_id: str, request: AlertToggleRequest
    ) -> SavedQuery | None:
        """Update alert parameters (enabled, paused, cooldown) for a user's saved query."""
        now = utc_now()
        update_data: dict[str, Any] = {
            "alerts_enabled": request.alerts_enabled,
            "is_paused": request.is_paused,
            "cooldown_hours": request.cooldown_hours,
            "updated_at": now,
        }
        res = self.saved_queries_col.find_one_and_update(
            {"user_id": user_id, "query_id": request.query_id},
            {"$set": update_data},
            return_document=True,
        )
        if not res:
            return None
        res.pop("_id", None)
        return SavedQuery.model_validate(res)

    def evaluate_article_alerts(self, article: dict[str, Any]) -> list[InAppNotification]:
        """Evaluate an article against all active, unpaused saved queries.

        Enforces:
        1. Query matching (keywords, source, language).
        2. Cooldown period (suppresses alert if last alert was within cooldown window).
        3. Dedup & Replay defense (atomic dedup insert guarantees zero duplicate notifications).
        """
        article_id = article.get("article_id", "")
        if not article_id:
            return []

        article_title = article.get("title", "")
        article_source = article.get("source_id", "")
        article_lang = article.get("language", "")
        article_body = article.get("body_text", "")

        active_queries_cursor = self.saved_queries_col.find(
            {"alerts_enabled": True, "is_paused": False}
        )

        generated_notifications: list[InAppNotification] = []
        now = utc_now()

        for q_doc in active_queries_cursor:
            raw_user_id = q_doc.get("user_id")
            raw_query_id = q_doc.get("query_id")
            if not raw_user_id or not raw_query_id:
                continue
            user_id = str(raw_user_id)
            query_id = str(raw_query_id)
            query_name = q_doc.get("name", "تنبيه استعلام")
            params = q_doc.get("query_params", {})
            cooldown_hours = q_doc.get("cooldown_hours", 1)
            last_alert_at = q_doc.get("last_alert_at")

            # Check cooldown period
            if last_alert_at:
                if isinstance(last_alert_at, str):
                    try:
                        last_alert_dt = datetime.fromisoformat(last_alert_at)
                    except ValueError:
                        last_alert_dt = None
                else:
                    last_alert_dt = last_alert_at

                if last_alert_dt and last_alert_dt.tzinfo is None:
                    last_alert_dt = last_alert_dt.replace(tzinfo=timezone.utc)

                if last_alert_dt and (now - last_alert_dt) < timedelta(hours=cooldown_hours):
                    # In cooldown period; suppress notification
                    continue

            # Check match against parameters
            if not self._matches_filter(
                params, article_title, article_body, article_source, article_lang
            ):
                continue

            # Replay and Dedup defense: try to insert dedup key
            recorded = self.notification_repo.record_notification_dedup(
                user_id=user_id,
                query_id=query_id,
                target_id=article_id,
            )
            if not recorded:
                # Already notified (replay idempotency); skip
                continue

            # Create notification
            notification = InAppNotification(
                user_id=user_id,
                title=f"تنبيه استعلام: {query_name}",
                message=f"مقال جديد متوافق مع استعلامك '{query_name}': {article_title[:120]}",
                notification_type="saved_query_match",
                target_type="article",
                target_id=article_id,
                target_version=article.get("version", 1),
                metadata={
                    "query_id": query_id,
                    "query_name": query_name,
                    "source_id": article_source,
                    "article_title": article_title,
                },
                created_at=now,
            )
            self.notification_repo.create_notification(notification)
            generated_notifications.append(notification)

            # Update last_alert_at
            self.saved_queries_col.update_one(
                {"query_id": query_id},
                {"$set": {"last_alert_at": now}},
            )

        return generated_notifications

    def evaluate_story_alerts(self, story: dict[str, Any]) -> list[InAppNotification]:
        """Evaluate story changes/emergence against active alerts with dedup."""
        story_id = story.get("story_id", "")
        if not story_id:
            return []

        story_title = story.get("title", "")
        story_version = story.get("version", 1)

        active_queries_cursor = self.saved_queries_col.find(
            {"alerts_enabled": True, "is_paused": False}
        )

        generated: list[InAppNotification] = []
        now = utc_now()

        for q_doc in active_queries_cursor:
            raw_user_id = q_doc.get("user_id")
            raw_query_id = q_doc.get("query_id")
            if not raw_user_id or not raw_query_id:
                continue
            user_id = str(raw_user_id)
            query_id = str(raw_query_id)
            query_name = q_doc.get("name", "تنبيه حدث")
            params = q_doc.get("query_params", {})

            # Match against story title
            q_term = (params.get("q") or "").strip().lower()
            if q_term and q_term not in story_title.lower():
                continue

            # Dedup defense using story_id and story_version to allow alerts on significant version updates
            target_key = f"{story_id}:v{story_version}"
            recorded = self.notification_repo.record_notification_dedup(
                user_id=user_id,
                query_id=query_id,
                target_id=target_key,
            )
            if not recorded:
                continue

            notification = InAppNotification(
                user_id=user_id,
                title=f"تحديث حدث: {story_title[:60]}",
                message=f"طرأ تحديث أو ظهور لحدث يتوافق مع بحثك '{query_name}': {story_title[:120]}",
                notification_type="story_update",
                target_type="story",
                target_id=story_id,
                target_version=story_version,
                metadata={"query_id": query_id, "story_title": story_title},
                created_at=now,
            )
            self.notification_repo.create_notification(notification)
            generated.append(notification)

        return generated

    def _matches_filter(
        self,
        params: dict[str, Any],
        title: str,
        body: str,
        source: str,
        lang: str,
    ) -> bool:
        """Check if article matches saved query criteria."""
        q_term = (params.get("q") or "").strip().lower()
        if q_term:
            in_title = q_term in title.lower()
            in_body = q_term in body.lower()
            if not in_title and not in_body:
                return False

        source_param = params.get("source_id")
        if source_param and source_param != source:
            return False

        lang_param = params.get("language")
        if lang_param and lang_param != lang:
            return False

        return True
