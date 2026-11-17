"""Service orchestrating article deduplication, candidate retrieval, and relationship management."""

import logging
from datetime import timedelta
from typing import Any

from pymongo.database import Database

from insightbot.models.article import Article
from insightbot.models.duplicate import (
    DuplicateRelationship,
)
from insightbot.modules.deduplication.detector import DeduplicationEngine
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.duplicate_repository import DuplicateRepository

logger = logging.getLogger(__name__)

ARTICLE_PROJECTION = {
    "_id": 0,
    "article_id": 1,
    "source_id": 1,
    "canonical_url": 1,
    "original_url": 1,
    "resolved_url": 1,
    "title": 1,
    "body_text": 1,
    "content_hash": 1,
    "language": 1,
    "published_at": 1,
    "fetched_at": 1,
    "word_count": 1,
    "stage_states": 1,
}


class DeduplicationService:
    """Orchestrates exact hash and near-duplicate detection while preserving publisher originals."""

    def __init__(
        self,
        db: Database[dict[str, Any]],
        detector: DeduplicationEngine | None = None,
    ):
        self.db = db
        self.articles_coll = db["articles"]
        self.article_repo = ArticleRepository(db)
        self.dup_repo = DuplicateRepository(db)
        self.detector = detector or DeduplicationEngine(
            near_duplicate_threshold=0.85,
            temporal_window_hours=72.0,
        )

    def deduplicate_article(self, article_id: str) -> list[DuplicateRelationship]:
        """
        Run deduplication for an article against exact-hash candidates and 72-hour window neighbors.
        Updates stage_states['deduplication'] = 'completed'.
        """
        doc = self.articles_coll.find_one({"article_id": article_id}, ARTICLE_PROJECTION)
        if not doc:
            logger.warning("Article '%s' not found for deduplication", article_id)
            return []

        target = Article.model_validate(doc)
        target_time = target.published_at or target.fetched_at

        # 1. Fetch exact content hash candidates (any time window)
        hash_query = {
            "content_hash": target.content_hash,
            "article_id": {"$ne": target.article_id},
        }
        candidate_docs = list(self.articles_coll.find(hash_query, ARTICLE_PROJECTION))

        # 2. Fetch temporal window candidates (within 72 hours)
        window = timedelta(hours=self.detector.temporal_window_hours)
        min_time = target_time - window
        max_time = target_time + window

        temporal_query = {
            "article_id": {"$ne": target.article_id},
            "content_hash": {"$ne": target.content_hash},  # already fetched above
            "$or": [
                {"published_at": {"$gte": min_time, "$lte": max_time}},
                {"fetched_at": {"$gte": min_time, "$lte": max_time}},
            ],
        }
        candidate_docs.extend(list(self.articles_coll.find(temporal_query, ARTICLE_PROJECTION).limit(100)))

        # Compare target against all candidates
        relationships: list[DuplicateRelationship] = []
        for c_doc in candidate_docs:
            candidate = Article.model_validate(c_doc)
            rel = self.detector.compare(target, candidate)
            if rel:
                saved = self.dup_repo.upsert_relationship(rel)
                relationships.append(saved)

        # Mark target deduplication stage as completed
        self.articles_coll.update_one(
            {"article_id": article_id},
            {"$set": {"stage_states.deduplication": "completed"}},
        )

        return relationships

    def run_batch_deduplication(self, limit: int = 50) -> int:
        """Batch process un-deduplicated articles."""
        cursor = self.articles_coll.find(
            {"stage_states.deduplication": {"$ne": "completed"}},
            {"article_id": 1},
        ).limit(limit)

        count = 0
        for doc in cursor:
            self.deduplicate_article(doc["article_id"])
            count += 1
        return count

    def get_duplicates_for_article_with_previews(
        self, article_id: str
    ) -> list[dict[str, Any]]:
        """
        Fetch all duplicate relationships for an article with related article previews.
        Excludes full body_text from previews to prevent memory exhaustion (Defect A12).
        """
        relationships = self.dup_repo.get_duplicates_for_article(article_id)
        results: list[dict[str, Any]] = []

        for rel in relationships:
            # Related article is the 'other' article in the pair
            other_id = (
                rel.duplicate_article_id
                if rel.canonical_article_id == article_id
                else rel.canonical_article_id
            )

            preview_doc = self.articles_coll.find_one(
                {"article_id": other_id},
                {
                    "_id": 0,
                    "article_id": 1,
                    "source_id": 1,
                    "title": 1,
                    "canonical_url": 1,
                    "published_at": 1,
                    "language": 1,
                    "word_count": 1,
                    "reading_time_minutes": 1,
                },
            )

            is_canonical = rel.canonical_article_id == article_id
            results.append(
                {
                    "relationship_id": rel.relationship_id,
                    "is_canonical": is_canonical,
                    "duplicate_type": rel.duplicate_type.value,
                    "status": rel.status.value,
                    "similarity_score": rel.similarity_score,
                    "evidence": rel.evidence.model_dump(),
                    "detected_at": rel.detected_at,
                    "related_article": preview_doc,
                }
            )

        return results
