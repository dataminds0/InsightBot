"""Background processing worker handling atomic leases, fencing tokens, and job reconciliation."""

import logging
from typing import Any, Optional
from uuid import uuid4

from pymongo.database import Database

from insightbot.config import Settings
from insightbot.models.job import Job, JobStatus
from insightbot.modules.ingestion.service import IngestionService
from insightbot.modules.sources.registry import load_sources_from_yaml
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.job_repository import JobRepository, StaleWorkerCommitError
from insightbot.repositories.source_repository import SourceRepository

logger = logging.getLogger(__name__)


class WorkerService:
    """Worker process coordinating job claiming, lease maintenance, and fencing-validated commits."""

    def __init__(
        self,
        db: Database[dict[str, Any]],
        settings: Settings,
        worker_id: Optional[str] = None,
    ):
        self.db = db
        self.settings = settings
        self.worker_id = worker_id or f"worker_{uuid4().hex[:8]}"
        self.job_repo = JobRepository(db)
        self.source_repo = SourceRepository(db)
        self.article_repo = ArticleRepository(db)
        self.ingestion_service = IngestionService(db=db, settings=settings)

    def process_one_job(self, kinds: Optional[list[str]] = None) -> Optional[Job]:
        """
        Claim and execute a single job.
        Validates fencing token before committing.
        Returns the committed Job or None if no job was available.
        """
        job = self.job_repo.claim_next_job(worker_id=self.worker_id, kinds=kinds)
        if not job:
            return None

        logger.info(
            "Worker '%s' processing job '%s' (kind: %s, target: %s)",
            self.worker_id,
            job.job_id,
            job.kind,
            job.target_id,
        )

        try:
            if job.kind == "ingest_source":
                result_status, result_data = self._handle_ingest_source(job)
            elif job.kind == "reconcile_article":
                result_status, result_data = self._handle_reconcile_article(job)
            else:
                result_status = JobStatus.FAILED
                result_data = {"error": f"Unknown job kind: '{job.kind}'"}

            # Atomic commit with fencing token
            committed_job = self.job_repo.commit_job(
                job_id=job.job_id,
                worker_id=self.worker_id,
                fencing_token=job.fencing_token,
                result_data=result_data,
                status=result_status,
            )
            return committed_job

        except StaleWorkerCommitError as stale_err:
            logger.warning(
                "Late commit rejected for worker '%s' on job '%s': %s",
                self.worker_id,
                job.job_id,
                stale_err,
            )
            raise
        except Exception as exc:
            logger.exception("Error executing job '%s': %s", job.job_id, exc)
            self.job_repo.fail_job(
                job_id=job.job_id,
                worker_id=self.worker_id,
                fencing_token=job.fencing_token,
                error_msg=str(exc),
            )
            return None

    def _handle_ingest_source(self, job: Job) -> tuple[JobStatus, dict[str, Any]]:
        """Handle source ingestion with strict disabled-by-default check."""
        source_id = job.target_id
        source = self.source_repo.get_by_id(source_id)

        # Fallback to YAML definitions if not yet synced to DB
        if not source and self.settings.sources_config_path.exists():
            sources = load_sources_from_yaml(self.settings.sources_config_path)
            source = next((s for s in sources if s.source_id == source_id), None)

        if not source:
            return JobStatus.FAILED, {"error": f"Source '{source_id}' not found in registry."}

        # Check disabled policy
        if not source.enabled and not job.payload.get("ignore_disabled", False):
            logger.info(
                "Source '%s' is disabled. Setting job status to skipped_disabled.", source_id
            )
            return JobStatus.SKIPPED_DISABLED, {
                "reason": "Source is disabled by policy.",
                "source_id": source_id,
            }

        limit = job.payload.get("limit", 10)
        report = self.ingestion_service.ingest_source(
            source=source,
            limit=limit,
            ignore_disabled=job.payload.get("ignore_disabled", False),
        )

        return JobStatus.COMPLETED, report.model_dump()

    def _handle_reconcile_article(self, job: Job) -> tuple[JobStatus, dict[str, Any]]:
        """Handle version pointer reconciliation for an article."""
        article_id = job.target_id
        reconciled = self.article_repo.reconcile_article_version(article_id)
        if not reconciled:
            return JobStatus.FAILED, {"error": f"Article '{article_id}' could not be reconciled."}

        return JobStatus.COMPLETED, {
            "article_id": article_id,
            "current_version": reconciled.current_version,
            "title": reconciled.title,
        }

    def run_bounded(self, max_jobs: int = 10, kinds: Optional[list[str]] = None) -> int:
        """Process up to max_jobs and return count of executed jobs."""
        executed = 0
        while executed < max_jobs:
            job = self.process_one_job(kinds=kinds)
            if not job:
                break
            executed += 1
        return executed
