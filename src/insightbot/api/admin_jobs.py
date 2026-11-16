"""Administrator background job inspection, scoped retry, and cancellation endpoints."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from insightbot.api.deps import (
    get_audit_repository,
    get_job_repository,
    get_source_repository,
    require_admin,
)
from insightbot.models.job import Job
from insightbot.models.user import User
from insightbot.repositories.audit_repository import AuditRepository
from insightbot.repositories.job_repository import JobRepository
from insightbot.repositories.source_repository import SourceRepository

router = APIRouter(prefix="/api/admin/jobs", tags=["Admin Jobs"])


class TriggerJobRequest(BaseModel):
    source_id: str
    limit: int = Field(default=20, ge=1, le=100)


class JobRunsResponse(BaseModel):
    jobs: list[Job]
    stats: dict[str, int]


@router.get("", response_model=JobRunsResponse)
def list_jobs(
    job_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    kind: Optional[str] = Query(None, description="Filter by job kind"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    job_repo: JobRepository = Depends(get_job_repository),
) -> JobRunsResponse:
    """List recent worker jobs and aggregate status metrics (Admin only)."""
    jobs = job_repo.list_jobs(status=job_status, kind=kind, limit=limit, skip=skip)
    stats = job_repo.get_job_stats()
    return JobRunsResponse(jobs=jobs, stats=stats)


@router.post("/{job_id}/retry", response_model=Job)
def retry_job(
    job_id: str,
    admin: User = Depends(require_admin),
    job_repo: JobRepository = Depends(get_job_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> Job:
    """Perform a scoped retry on a failed or cancelled job (Admin only)."""
    retried = job_repo.retry_job(job_id)
    if not retried:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' was not found.",
        )

    audit_repo.record(
        actor_id=admin.user_id,
        action="retry_job",
        entity_type="job",
        entity_id=job_id,
        details={"kind": retried.kind, "target_id": retried.target_id},
    )
    return retried


@router.post("/{job_id}/cancel", response_model=dict[str, Any])
def cancel_job(
    job_id: str,
    admin: User = Depends(require_admin),
    job_repo: JobRepository = Depends(get_job_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> dict[str, Any]:
    """Cancel a running or pending job lease (Admin only)."""
    success = job_repo.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job '{job_id}' could not be cancelled. It may already be completed or not exist.",
        )

    audit_repo.record(
        actor_id=admin.user_id,
        action="cancel_job",
        entity_type="job",
        entity_id=job_id,
    )
    return {"message": f"Job '{job_id}' was cancelled.", "job_id": job_id}


@router.post("/trigger", response_model=Job, status_code=status.HTTP_201_CREATED)
def trigger_source_ingestion(
    req: TriggerJobRequest,
    admin: User = Depends(require_admin),
    source_repo: SourceRepository = Depends(get_source_repository),
    job_repo: JobRepository = Depends(get_job_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
) -> Job:
    """Trigger a bounded ingestion job for a specific source (Admin only)."""
    source = source_repo.get_by_id(req.source_id)
    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{req.source_id}' was not found in registry.",
        )

    job = job_repo.create_job(
        kind="ingest_source",
        target_id=req.source_id,
        payload={"limit": req.limit},
    )

    audit_repo.record(
        actor_id=admin.user_id,
        action="trigger_job",
        entity_type="job",
        entity_id=job.job_id,
        details={"kind": job.kind, "target_id": req.source_id, "limit": req.limit},
    )
    return job
