"""Analyst Assistant API: query execution, asynchronous jobs, and cancellation."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from insightbot.api.deps import (
    get_assistant_repository,
    get_assistant_service,
    require_analyst,
)
from insightbot.models.assistant import (
    AssistantAskRequest,
    AssistantJob,
    AssistantJobResponse,
)
from insightbot.models.generation import GenerationOutput
from insightbot.models.user import Role, User
from insightbot.modules.assistant.service import AssistantService
from insightbot.repositories.assistant_repository import (
    AssistantJobRepository,
    AssistantQueueFullError,
)

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


@router.post(
    "/ask",
    response_model=GenerationOutput | AssistantJobResponse,
)
def ask_assistant(
    payload: AssistantAskRequest,
    async_mode: bool = Query(False, description="Run query asynchronously with job polling"),
    current_user: User = Depends(require_analyst),
    service: AssistantService = Depends(get_assistant_service),
) -> Any:
    """Submit a question to the local analyst assistant with citation verification.

    If async_mode is True, returns 202 Accepted with job status and queue position.
    Otherwise, runs synchronously within the 120s deadline and returns GenerationOutput.
    """
    try:
        if async_mode:
            job, pos = service.submit_question(user_id=current_user.user_id, request=payload)
            return AssistantJobResponse(job=job, queue_position=pos)

        # Synchronous execution
        return service.ask_sync(user_id=current_user.user_id, request=payload)
    except AssistantQueueFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


@router.get("/jobs", response_model=list[AssistantJob])
def list_assistant_jobs(
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(require_analyst),
    repo: AssistantJobRepository = Depends(get_assistant_repository),
) -> list[AssistantJob]:
    """List recent assistant query jobs for the authenticated user."""
    return repo.list_user_jobs(user_id=current_user.user_id, limit=limit)


@router.get("/jobs/{job_id}", response_model=AssistantJob)
def get_assistant_job(
    job_id: str,
    current_user: User = Depends(require_analyst),
    repo: AssistantJobRepository = Depends(get_assistant_repository),
) -> AssistantJob:
    """Get the status and result of an assistant job with owner authorization defense."""
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assistant job {job_id} not found.",
        )

    # Owner isolation / IDOR guard
    if job.user_id != current_user.user_id and current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Cannot access another user's assistant job.",
        )

    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_assistant_job(
    job_id: str,
    current_user: User = Depends(require_analyst),
    service: AssistantService = Depends(get_assistant_service),
    repo: AssistantJobRepository = Depends(get_assistant_repository),
) -> dict[str, Any]:
    """Cancel a pending or processing assistant job."""
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assistant job {job_id} not found.",
        )

    if job.user_id != current_user.user_id and current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Cannot cancel another user's assistant job.",
        )

    success = service.cancel_job(job_id=job_id, user_id=current_user.user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel job; it may have already completed, failed, or been cancelled.",
        )

    return {"status": "cancelled", "job_id": job_id}
