"""Repository managing asynchronous assistant query jobs and queue constraints."""

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.assistant import AssistantJob, AssistantJobStatus
from insightbot.models.generation import GenerationOutput

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class AssistantQueueFullError(Exception):
    """Raised when the assistant queue exceeds its concurrency limit."""


class AssistantJobRepository:
    """Handles persistence, status transitions, and bounded queue limits for assistant queries."""

    MAX_QUEUED_JOBS: int = 2

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.jobs = db["assistant_jobs"]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes for job lookup and status management."""
        try:
            self.jobs.create_index([("job_id", 1)], unique=True)
            self.jobs.create_index([("user_id", 1), ("created_at", -1)])
            self.jobs.create_index([("status", 1), ("created_at", 1)])
        except Exception as exc:
            logger.warning("AssistantJobRepository index creation notice: %s", exc)

    def enqueue_job(self, job: AssistantJob) -> tuple[AssistantJob, int]:
        """Enqueue an assistant job if within queue limit, returning (job, queue_position)."""
        pending_count = self.jobs.count_documents(
            {"user_id": job.user_id, "status": {"$in": ["pending", "processing"]}}
        )
        if pending_count >= self.MAX_QUEUED_JOBS:
            raise AssistantQueueFullError(
                f"Assistant job queue limit exceeded ({self.MAX_QUEUED_JOBS} active/queued jobs max)."
            )

        doc = job.model_dump()
        self.jobs.insert_one(doc)
        queue_pos = self.jobs.count_documents(
            {"status": "pending", "created_at": {"$lte": job.created_at}}
        )
        return job, queue_pos

    def get_job(self, job_id: str) -> AssistantJob | None:
        """Retrieve an assistant job by ID."""
        doc = self.jobs.find_one({"job_id": job_id}, {"_id": 0})
        if not doc:
            return None
        return AssistantJob.model_validate(doc)

    def list_user_jobs(self, user_id: str, limit: int = 20) -> list[AssistantJob]:
        """List assistant jobs for a user ordered newest first."""
        cursor = (
            self.jobs.find({"user_id": user_id}, {"_id": 0})
            .sort("created_at", -1)
            .limit(limit)
        )
        return [AssistantJob.model_validate(doc) for doc in cursor]

    def cancel_job(self, job_id: str, user_id: str) -> bool:
        """Cancel a pending or processing assistant job."""
        res = self.jobs.update_one(
            {
                "job_id": job_id,
                "user_id": user_id,
                "status": {"$in": ["pending", "processing"]},
            },
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_by": user_id,
                    "completed_at": utc_now(),
                }
            },
        )
        return res.modified_count > 0

    def update_job_status(
        self,
        job_id: str,
        status: AssistantJobStatus,
        result: GenerationOutput | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update job lifecycle status and optional result/error."""
        update_doc: dict[str, Any] = {"status": status}
        now = utc_now()
        if status == "processing":
            update_doc["started_at"] = now
        elif status in ("completed", "failed", "cancelled"):
            update_doc["completed_at"] = now

        if result is not None:
            update_doc["result"] = result.model_dump()
        if error_message is not None:
            update_doc["error_message"] = error_message

        res = self.jobs.update_one({"job_id": job_id}, {"$set": update_doc})
        return res.modified_count > 0
