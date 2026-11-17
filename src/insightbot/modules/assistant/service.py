"""Analyst assistant service with bounded budgets, job cancellation, and citation validation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.assistant import AssistantAskRequest, AssistantJob
from insightbot.models.generation import GenerationInput, GenerationOutput
from insightbot.modules.generation.engine import LocalEvidenceGenerationEngine
from insightbot.modules.generation.service import GenerationService
from insightbot.repositories.assistant_repository import AssistantJobRepository

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class AssistantService:
    """Coordinates analyst queries, execution jobs, cancellation, and citation availability validation."""

    MAX_QUERY_CHARS: int = 2000
    DEADLINE_SECONDS: int = 120

    def __init__(
        self,
        db: Database[dict[str, Any]],
        assistant_repo: AssistantJobRepository,
        generation_service: GenerationService,
        engine: LocalEvidenceGenerationEngine,
    ):
        self.db = db
        self.assistant_repo = assistant_repo
        self.generation_service = generation_service
        self.engine = engine
        self.articles_col = db["articles"]
        self.revisions_col = db["article_revisions"]

    def submit_question(self, user_id: str, request: AssistantAskRequest) -> tuple[AssistantJob, int]:
        """Submit an analyst question as an asynchronous job with deadline and budget enforcement."""
        if len(request.query) > self.MAX_QUERY_CHARS:
            raise ValueError(
                f"Question exceeds maximum character budget of {self.MAX_QUERY_CHARS} characters."
            )

        now = utc_now()
        deadline = now + timedelta(seconds=self.DEADLINE_SECONDS)

        job = AssistantJob(
            user_id=user_id,
            query=request.query,
            story_id=request.story_id,
            source_id=request.source_id,
            max_passages=request.max_passages,
            status="pending",
            created_at=now,
            deadline_at=deadline,
        )

        return self.assistant_repo.enqueue_job(job)

    def process_job(self, job_id: str) -> AssistantJob:
        """Execute a pending assistant job with citation availability verification."""
        job = self.assistant_repo.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found.")

        if job.status == "cancelled":
            return job

        self.assistant_repo.update_job_status(job_id, "processing")

        try:
            gen_input = GenerationInput(
                query=job.query,
                story_id=job.story_id,
                source_id=job.source_id,
                max_passages=job.max_passages,
            )

            result = self.generation_service.ask_question(gen_input)

            # Validate citation availability (Defect A13 / Section 13 requirement)
            validated_result = self._validate_citations_availability(result)

            # Check if job was cancelled while processing
            current_job = self.assistant_repo.get_job(job_id)
            if current_job and current_job.status == "cancelled":
                return current_job

            self.assistant_repo.update_job_status(job_id, "completed", result=validated_result)
            updated = self.assistant_repo.get_job(job_id)
            return updated or job

        except Exception as exc:
            logger.exception("Assistant job %s failed: %s", job_id, exc)
            self.assistant_repo.update_job_status(job_id, "failed", error_message=str(exc))
            updated = self.assistant_repo.get_job(job_id)
            return updated or job

    def ask_sync(self, user_id: str, request: AssistantAskRequest) -> GenerationOutput:
        """Directly answer a question synchronously with citation validation."""
        if len(request.query) > self.MAX_QUERY_CHARS:
            raise ValueError(
                f"Question exceeds maximum character budget of {self.MAX_QUERY_CHARS} characters."
            )

        gen_input = GenerationInput(
            query=request.query,
            story_id=request.story_id,
            source_id=request.source_id,
            max_passages=request.max_passages,
        )

        result = self.generation_service.ask_question(gen_input)
        return self._validate_citations_availability(result)

    def cancel_job(self, job_id: str, user_id: str) -> bool:
        """Cancel a pending or processing assistant job."""
        return self.assistant_repo.cancel_job(job_id, user_id)

    def _validate_citations_availability(self, output: GenerationOutput) -> GenerationOutput:
        """Verify each citation exists in repository and has not been quarantined or deleted.

        Historical evidence must open its specific version or report explicit unavailability,
        never silently link to a different or latest version.
        """
        for cit in output.citations:
            article = self.articles_col.find_one({"article_id": cit.article_id})
            if not article:
                # Article was deleted or unavailable
                cit.is_valid = False
                cit.quote = "[المحتوى الأصلي غير متاح حالياً / Target unavailable]"
                continue

            if article.get("quarantined", False):
                # Quarantined due to extraction or legal defect
                cit.is_valid = False
                cit.quote = "[المقال في الحجر الصحي / Article quarantined]"
                continue

            # Verify version match
            current_version = article.get("version", 1)
            if cit.version != current_version:
                # Historical revision: check if revision exists
                revision = self.revisions_col.find_one(
                    {"article_id": cit.article_id, "version": cit.version}
                )
                if not revision:
                    cit.is_valid = False
                    cit.quote = f"[الإصدار التاريخي v{cit.version} غير متاح]"

        return output
