"""Service orchestrating story clustering, lifecycle management, and audited merges/splits."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.article import Article
from insightbot.models.story import (
    EntityCategory,
    Story,
    StoryAudit,
    StoryStatus,
)
from insightbot.modules.stories.clustering import (
    StoryClusteringEngine,
    extract_entities_from_text,
    extract_keywords_from_text,
)
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.story_repository import StoryRepository

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
    "published_at": 1,
    "fetched_at": 1,
    "word_count": 1,
    "reading_time_minutes": 1,
    "stage_states": 1,
}


class StoryService:
    """Orchestrates story clustering with chain-merge and location protection."""

    def __init__(
        self,
        db: Database[dict[str, Any]],
        clustering_engine: StoryClusteringEngine | None = None,
    ):
        self.db = db
        self.articles_coll = db["articles"]
        self.stories_coll = db["stories"]
        self.article_repo = ArticleRepository(db)
        self.story_repo = StoryRepository(db)
        self.engine = clustering_engine or StoryClusteringEngine(
            headline_similarity_threshold=0.55,
            shingle_similarity_threshold=0.45,
            temporal_window_hours=72.0,
        )

    def cluster_article(self, article_id: str, actor_id: str = "system_worker") -> Story:
        """
        Assign an article to an existing story cluster or create a new emerging event cluster.
        Guarantees location conflict protection and chain-merge defenses.
        """
        # Check if already clustered
        existing_story = self.story_repo.get_story_for_article(article_id)
        if existing_story:
            return existing_story

        doc = self.articles_coll.find_one({"article_id": article_id}, ARTICLE_PROJECTION)
        if not doc:
            raise ValueError(f"Article '{article_id}' not found")

        article = Article.model_validate(doc)
        art_time = article.published_at or article.fetched_at

        # 1. Extract and persist entities
        mentions = extract_entities_from_text(
            article_id, article.title + "\n\n" + article.body_text
        )
        self.story_repo.save_entity_mentions(mentions)

        loc_entities = [
            m.resolved_id
            for m in mentions
            if m.category == EntityCategory.LOCATION and m.resolved_id
        ]
        org_entities = [
            m.resolved_id
            for m in mentions
            if m.category == EntityCategory.ORGANIZATION and m.resolved_id
        ]
        primary_loc = loc_entities[0] if loc_entities else None
        extracted_keywords = extract_keywords_from_text(article.title, article.body_text)

        # 2. Retrieve active candidate stories within 72 hours
        window = timedelta(hours=self.engine.temporal_window_hours)
        min_time = art_time - window
        max_time = art_time + window

        candidate_query = {
            "status": {"$ne": StoryStatus.CLOSED.value},
            "$or": [
                {"first_article_at": {"$gte": min_time, "$lte": max_time}},
                {"last_article_at": {"$gte": min_time, "$lte": max_time}},
                {"updated_at": {"$gte": min_time, "$lte": max_time}},
            ],
        }

        candidate_docs = list(self.stories_coll.find(candidate_query, {"_id": 0}).limit(50))

        best_story: Story | None = None
        best_score = -1.0
        best_reason = ""

        for s_doc in candidate_docs:
            candidate_story = Story.model_validate(s_doc)

            # Retrieve lead article of the candidate story for chain-merge comparison
            lead_art = None
            if candidate_story.lead_article_id:
                lead_doc = self.articles_coll.find_one(
                    {"article_id": candidate_story.lead_article_id}, ARTICLE_PROJECTION
                )
                if lead_doc:
                    lead_art = Article.model_validate(lead_doc)

            belongs, score, reason = self.engine.evaluate_membership(
                article, candidate_story, lead_art
            )
            if belongs and score > best_score:
                best_story = candidate_story
                best_score = score
                best_reason = reason

        # 3. Assign to best matching story or create new one
        if best_story:
            updated = self.story_repo.add_article_to_story(
                story_id=best_story.story_id,
                article=article,
                actor_id=actor_id,
                reason=f"clustering: {best_reason}",
            )
            result_story = updated
        else:
            now = datetime.now(timezone.utc)
            new_story = Story(
                title=article.title,
                summary="",
                status=StoryStatus.EMERGING,
                lead_article_id=article.article_id,
                article_ids=[article.article_id],
                sources=[article.source_id],
                article_count=1,
                sources_count=1,
                first_article_at=art_time,
                last_article_at=art_time,
                created_at=now,
                updated_at=now,
                primary_location=primary_loc,
                keywords=extracted_keywords,
                entities=list(set(loc_entities + org_entities)),
                version=1,
            )
            result_story = self.story_repo.create_story(
                new_story, actor_id=actor_id, reason="new_emerging_event"
            )

        # 4. Mark article stage state as completed
        self.articles_coll.update_one(
            {"article_id": article_id},
            {"$set": {"stage_states.stories": "completed"}},
        )

        return result_story

    def get_story_detail(self, story_id: str) -> dict[str, Any] | None:
        """
        Retrieve story cluster with member article previews.
        Excludes full body_text from previews to defend against whole-corpus memory exhaustion (Defect A12).
        """
        story = self.story_repo.get_story_by_id(story_id)
        if not story:
            return None

        # Fetch member article previews
        member_docs = list(
            self.articles_coll.find(
                {"article_id": {"$in": story.article_ids}},
                {
                    "_id": 0,
                    "article_id": 1,
                    "source_id": 1,
                    "canonical_url": 1,
                    "title": 1,
                    "language": 1,
                    "published_at": 1,
                    "fetched_at": 1,
                    "word_count": 1,
                    "reading_time_minutes": 1,
                },
            )
        )

        data = story.model_dump()
        data["member_articles"] = member_docs
        return data

    def merge_stories(
        self,
        target_story_id: str,
        source_story_id: str,
        actor_id: str,
        reason: str,
    ) -> Story:
        """Audited merge of two stories."""
        return self.story_repo.merge_stories(
            target_story_id=target_story_id,
            source_story_id=source_story_id,
            actor_id=actor_id,
            reason=reason,
        )

    def split_story(
        self,
        source_story_id: str,
        article_ids_to_split: list[str],
        new_title: str,
        actor_id: str,
        reason: str,
    ) -> tuple[Story, Story]:
        """Audited split of articles from a story into a new story."""
        return self.story_repo.split_story(
            source_story_id=source_story_id,
            article_ids_to_split=article_ids_to_split,
            new_title=new_title,
            actor_id=actor_id,
            reason=reason,
        )

    def list_stories(
        self,
        status: StoryStatus | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, int]:
        """Paginated list of stories."""
        return self.story_repo.list_stories(status=status, limit=limit, cursor=cursor)

    def get_story_history(self, story_id: str) -> list[StoryAudit]:
        """Get chronological audit history of a story."""
        return self.story_repo.get_story_history(story_id)

    def run_batch_clustering(self, limit: int = 50) -> int:
        """Batch cluster un-clustered articles."""
        cursor = self.articles_coll.find(
            {"stage_states.stories": {"$ne": "completed"}},
            {"article_id": 1},
        ).limit(limit)

        count = 0
        for doc in cursor:
            self.cluster_article(doc["article_id"])
            count += 1
        return count
