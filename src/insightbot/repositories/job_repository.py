"""Background task repository with atomic leases, fencing tokens, and lease reclamation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo.database import Database

from insightbot.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


class StaleWorkerCommitError(Exception):
    """Raised when a worker attempts to commit results after its lease has been reclaimed."""

    pass


class JobRepository:
    """Repository managing background jobs, atomic lease acquisition, and fencing token validation."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.jobs = db["jobs"]

    def create_job(
        self,
        kind: str,
        target_id: str,
        payload: Optional[dict[str, Any]] = None,
        max_attempts: int = 3,
    ) -> Job:
        """
        Create a job idempotently. If an active job for the same target and kind exists,
        returns the existing job to prevent redundant queuing.
        """
        existing = self.jobs.find_one(
            {
                "kind": kind,
                "target_id": target_id,
                "status": {"$in": [JobStatus.PENDING.value, JobStatus.RUNNING.value]},
            }
        )
        if existing:
            existing.pop("_id", None)
            return Job.model_validate(existing)

        job = Job(
            kind=kind,
            target_id=target_id,
            payload=payload or {},
            max_attempts=max_attempts,
        )
        self.jobs.insert_one(job.model_dump())
        return job

    def get_by_id(self, job_id: str) -> Optional[Job]:
        """Fetch job by unique job_id."""
        doc = self.jobs.find_one({"job_id": job_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return Job.model_validate(doc)

    def claim_next_job(
        self,
        worker_id: str,
        kinds: Optional[list[str]] = None,
        lease_duration: timedelta = timedelta(minutes=5),
    ) -> Optional[Job]:
        """
        Atomically claim the next eligible job.
        Eligible jobs are either PENDING or RUNNING with an expired lease.
        Increments the fencing_token so any previous worker on this job is immediately invalidated.
        """
        now = datetime.now(timezone.utc)
        filter_query: dict[str, Any] = {
            "$or": [
                {"status": JobStatus.PENDING.value},
                {
                    "status": JobStatus.RUNNING.value,
                    "lease_expires_at": {"$lt": now},
                },
            ],
            "$expr": {"$lt": ["$attempts", "$max_attempts"]},
        }
        if kinds:
            filter_query["kind"] = {"$in": kinds}

        doc = self.jobs.find_one_and_update(
            filter_query,
            {
                "$set": {
                    "status": JobStatus.RUNNING.value,
                    "lease_owner": worker_id,
                    "lease_expires_at": now + lease_duration,
                    "updated_at": now,
                },
                "$inc": {
                    "fencing_token": 1,
                    "attempts": 1,
                },
            },
            return_document=True,
        )

        if not doc:
            return None

        doc.pop("_id", None)
        claimed_job = Job.model_validate(doc)
        logger.info(
            "Worker '%s' claimed job '%s' (%s: %s) with fencing_token=%d",
            worker_id,
            claimed_job.job_id,
            claimed_job.kind,
            claimed_job.target_id,
            claimed_job.fencing_token,
        )
        return claimed_job

    def commit_job(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        result_data: Optional[dict[str, Any]] = None,
        status: JobStatus = JobStatus.COMPLETED,
    ) -> Job:
        """
        Commit results for a completed job.
        Strictly verifies that fencing_token and lease_owner match the active claim.
        If another worker has reclaimed the lease, raises StaleWorkerCommitError and rejects late commit.
        """
        now = datetime.now(timezone.utc)
        doc = self.jobs.find_one_and_update(
            {
                "job_id": job_id,
                "status": JobStatus.RUNNING.value,
                "lease_owner": worker_id,
                "fencing_token": fencing_token,
            },
            {
                "$set": {
                    "status": status.value,
                    "result_data": result_data or {},
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            },
            return_document=True,
        )

        if not doc:
            logger.warning(
                "Late commit rejected for job '%s' by worker '%s' (fencing_token=%d). Lease was reclaimed or cancelled.",
                job_id,
                worker_id,
                fencing_token,
            )
            raise StaleWorkerCommitError(
                f"Commit rejected for job '{job_id}': lease was reclaimed by another worker or job was cancelled."
            )

        doc.pop("_id", None)
        return Job.model_validate(doc)

    def fail_job(
        self,
        job_id: str,
        worker_id: str,
        fencing_token: int,
        error_msg: str,
    ) -> bool:
        """
        Record failure for a job. If maximum attempts exceeded, moves to FAILED;
        otherwise resets to PENDING for retry.
        """
        now = datetime.now(timezone.utc)
        job = self.get_by_id(job_id)
        if not job or job.lease_owner != worker_id or job.fencing_token != fencing_token:
            return False

        new_status = (
            JobStatus.FAILED.value if job.attempts >= job.max_attempts else JobStatus.PENDING.value
        )
        res = self.jobs.update_one(
            {
                "job_id": job_id,
                "fencing_token": fencing_token,
            },
            {
                "$set": {
                    "status": new_status,
                    "error": error_msg,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            },
        )
        return res.modified_count > 0

    def list_jobs(
        self,
        status: Optional[str] = None,
        kind: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> list[Job]:
        """List background worker jobs ordered by updated_at descending."""
        query: dict[str, Any] = {}
        if status:
            query["status"] = status
        if kind:
            query["kind"] = kind

        cursor = self.jobs.find(query).sort("updated_at", -1).skip(skip).limit(limit)
        results: list[Job] = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(Job.model_validate(doc))
        return results

    def retry_job(self, job_id: str) -> Optional[Job]:
        """Reset a failed or cancelled job to PENDING so it can be reclaimed."""
        now = datetime.now(timezone.utc)
        doc = self.jobs.find_one_and_update(
            {"job_id": job_id},
            {
                "$set": {
                    "status": JobStatus.PENDING.value,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "error": None,
                    "attempts": 0,
                    "updated_at": now,
                },
                "$inc": {"fencing_token": 1},
            },
            return_document=True,
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return Job.model_validate(doc)

    def get_job_stats(self) -> dict[str, int]:
        """Aggregate counts per job status."""
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        results = {s.value: 0 for s in JobStatus}
        for item in self.jobs.aggregate(pipeline):
            status_val = item["_id"]
            if status_val in results:
                results[status_val] = item["count"]
        return results

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or running job."""
        now = datetime.now(timezone.utc)
        res = self.jobs.update_one(
            {
                "job_id": job_id,
                "status": {"$in": [JobStatus.PENDING.value, JobStatus.RUNNING.value]},
            },
            {
                "$set": {
                    "status": JobStatus.CANCELLED.value,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                }
            },
        )
        return res.modified_count > 0
