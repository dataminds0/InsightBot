"""API endpoints for Local Evidence-backed Generation, Q&A, and Story Briefings."""

from fastapi import APIRouter, Depends, HTTPException, status

from insightbot.api.deps import (
    get_generation_service,
    require_analyst,
    require_viewer,
)
from insightbot.models.generation import (
    GenerationInput,
    GenerationOutput,
    StoryBriefingResponse,
)
from insightbot.models.user import User
from insightbot.modules.generation.service import GenerationService

router = APIRouter(prefix="/api/generation", tags=["generation"])


@router.post("/ask", response_model=GenerationOutput)
def ask_question(
    payload: GenerationInput,
    current_user: User = Depends(require_analyst),
    service: GenerationService = Depends(get_generation_service),
) -> GenerationOutput:
    """
    Analyst analytical question answering backed by verifiable evidence citations.
    Enforces calibrated abstention when evidence in the archive is insufficient.
    """
    return service.ask_question(payload)


@router.get("/story/{story_id}/briefing", response_model=StoryBriefingResponse)
def get_story_briefing(
    story_id: str,
    current_user: User = Depends(require_viewer),
    service: GenerationService = Depends(get_generation_service),
) -> StoryBriefingResponse:
    """
    Retrieve or synthesize a structured factual briefing for an event story cluster.
    Guarantees stale cache invalidation when story version changes.
    """
    try:
        return service.get_or_create_story_briefing(story_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
