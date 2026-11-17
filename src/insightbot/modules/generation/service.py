"""Service orchestrating evidence retrieval, verification, and story briefing caching."""

import logging
from typing import Any

from pymongo.database import Database

from insightbot.models.generation import (
    GenerationInput,
    GenerationOutput,
    StoryBriefingResponse,
    utc_now,
)
from insightbot.modules.generation.engine import (
    CandidatePassage,
    LocalEvidenceGenerationEngine,
)
from insightbot.modules.search.service import SearchService

logger = logging.getLogger(__name__)


class GenerationService:
    """Manages evidence-backed analytical synthesis, briefing caching, and citation verification."""

    def __init__(
        self,
        db: Database[dict[str, Any]],
        engine: LocalEvidenceGenerationEngine | None = None,
        search_service: SearchService | None = None,
    ):
        self.db = db
        self.articles_coll = db["articles"]
        self.stories_coll = db["stories"]
        self.briefings_coll = db["story_briefings"]
        self.engine = engine or LocalEvidenceGenerationEngine()
        self.search_service = search_service or SearchService(db)

    def ask_question(self, gen_input: GenerationInput) -> GenerationOutput:
        """
        Answers an analytical query backed by verifiable evidence passages.
        Enforces calibrated abstention when evidence is insufficient or irrelevant.
        """
        passages: list[CandidatePassage] = []

        if gen_input.story_id:
            # Retrieve evidence directly from target story's member articles
            story_doc = self.stories_coll.find_one({"story_id": gen_input.story_id})
            if story_doc:
                art_ids = story_doc.get("article_ids", [])
                cursor = self.articles_coll.find(
                    {"article_id": {"$in": art_ids}},
                    {
                        "_id": 0,
                        "article_id": 1,
                        "source_id": 1,
                        "title": 1,
                        "body_text": 1,
                        "canonical_url": 1,
                        "current_version": 1,
                    },
                ).limit(gen_input.max_passages)

                for art in cursor:
                    body = (art.get("body_text") or art.get("title") or "").strip()
                    passages.append(
                        CandidatePassage(
                            article_id=art.get("article_id", ""),
                            version=art.get("current_version", 1),
                            source_id=art.get("source_id", "unknown"),
                            title=art.get("title", ""),
                            canonical_url=art.get("canonical_url", ""),
                            text=body[:300],
                            relevance_score=0.9,
                        )
                    )
        else:
            # Retrieve top passages from SearchService
            try:
                search_res = self.search_service.search(
                    query=gen_input.query,
                    source_id=gen_input.source_id,
                    limit=gen_input.max_passages,
                )

                for item in search_res.items:
                    # Score normalization for relevance
                    score = min(1.0, max(0.1, item.score))
                    passages.append(
                        CandidatePassage(
                            article_id=item.article_id,
                            version=1,
                            source_id=item.source_id,
                            title=item.title,
                            canonical_url=item.canonical_url,
                            text=item.snippet or item.title,
                            relevance_score=score,
                        )
                    )
            except Exception as e:
                logger.warning(f"Search retrieval fallback during generation: {e}")
                # Fallback to direct MongoDB regex match
                cursor = self.articles_coll.find(
                    {"$text": {"$search": gen_input.query}} if "$text" in gen_input.query else {"title": {"$regex": gen_input.query[:30], "$options": "i"}},
                    {"_id": 0, "article_id": 1, "source_id": 1, "title": 1, "body_text": 1, "canonical_url": 1, "current_version": 1},
                ).limit(gen_input.max_passages)

                for art in cursor:
                    body = (art.get("body_text") or art.get("title") or "").strip()
                    passages.append(
                        CandidatePassage(
                            article_id=art.get("article_id", ""),
                            version=art.get("current_version", 1),
                            source_id=art.get("source_id", "unknown"),
                            title=art.get("title", ""),
                            canonical_url=art.get("canonical_url", ""),
                            text=body[:300],
                            relevance_score=0.5,
                        )
                    )

        # Execute generation with calibrated abstention
        output = self.engine.generate(
            query=gen_input.query,
            passages=passages,
            max_passages=gen_input.max_passages,
        )

        # Citation Verification: ensure all cited article_ids actually exist
        for cit in output.citations:
            doc = self.articles_coll.find_one({"article_id": cit.article_id}, {"_id": 0, "article_id": 1})
            if not doc:
                cit.is_valid = False

        return output

    def get_or_create_story_briefing(self, story_id: str) -> StoryBriefingResponse:
        """
        Retrieves or synthesizes an evidence-backed factual briefing for an event story.
        Invalidates cached briefings when the story version increments (Defect defense: stale summary detection).
        """
        story_doc = self.stories_coll.find_one({"story_id": story_id})
        if not story_doc:
            raise ValueError(f"Story '{story_id}' not found")

        story_version = story_doc.get("version", 1)

        # Check cache
        cached = self.briefings_coll.find_one({"story_id": story_id})
        if cached and cached.get("story_version") == story_version:
            cached.pop("_id", None)
            return StoryBriefingResponse.model_validate(cached)

        # Generate fresh briefing from member articles
        art_ids = story_doc.get("article_ids", [])
        articles = list(
            self.articles_coll.find(
                {"article_id": {"$in": art_ids}},
                {
                    "_id": 0,
                    "article_id": 1,
                    "source_id": 1,
                    "title": 1,
                    "body_text": 1,
                    "canonical_url": 1,
                    "current_version": 1,
                },
            ).limit(6)
        )

        passages = [
            CandidatePassage(
                article_id=a["article_id"],
                version=a.get("current_version", 1),
                source_id=a.get("source_id", "unknown"),
                title=a.get("title", ""),
                canonical_url=a.get("canonical_url", ""),
                text=(a.get("body_text") or a.get("title") or "")[:250],
                relevance_score=0.95,
            )
            for a in articles
        ]

        gen_out = self.engine.generate(
            query=f"إيجاز وقائع الحدث: {story_doc.get('title')}",
            passages=passages,
            max_passages=6,
        )

        briefing = StoryBriefingResponse(
            story_id=story_id,
            story_title=story_doc.get("title", ""),
            story_version=story_version,
            briefing_markdown=gen_out.answer_markdown,
            claims=gen_out.claims,
            citations=gen_out.citations,
            abstained=gen_out.abstained,
            abstention_reason=gen_out.abstention_reason,
            generated_at=utc_now(),
            is_stale=False,
        )

        # Upsert in cache
        self.briefings_coll.update_one(
            {"story_id": story_id},
            {"$set": briefing.model_dump()},
            upsert=True,
        )

        return briefing
