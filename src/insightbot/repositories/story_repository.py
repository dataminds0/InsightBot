"""Repository managing Story clusters, Lifecycle transitions, Snapshots, and Audited Merges/Splits."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from insightbot.models.article import Article
from insightbot.models.story import (
    EntityMention,
    Story,
    StoryAudit,
    StoryAuditAction,
    StorySnapshot,
    StoryStatus,
)

logger = logging.getLogger(__name__)

STORY_PROJECTION = {
    "_id": 0,
    "story_id": 1,
    "title": 1,
    "summary": 1,
    "status": 1,
    "lead_article_id": 1,
    "article_ids": 1,
    "sources": 1,
    "article_count": 1,
    "sources_count": 1,
    "first_article_at": 1,
    "last_article_at": 1,
    "created_at": 1,
    "updated_at": 1,
    "peak_at": 1,
    "closed_at": 1,
    "primary_location": 1,
    "keywords": 1,
    "entities": 1,
    "version": 1,
}


class StoryRepository:
    """Manages persistent Story state, historical snapshots, and immutable audit logs."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.stories_coll = db["stories"]
        self.snapshots_coll = db["story_snapshots"]
        self.audits_coll = db["story_audits"]
        self.entities_coll = db["entity_mentions"]

    def create_story(
        self,
        story: Story,
        actor_id: str = "system_worker",
        reason: str = "initial_event_cluster",
    ) -> Story:
        """Create new story cluster, capture initial snapshot, and append audit record."""
        doc = story.model_dump()
        self.stories_coll.insert_one(doc)

        # Snapshot version 1
        snapshot = StorySnapshot(
            story_id=story.story_id,
            version=story.version,
            story_data=doc,
        )
        self.snapshots_coll.insert_one(snapshot.model_dump())

        # Audit log
        audit = StoryAudit(
            story_id=story.story_id,
            action=StoryAuditAction.CREATED,
            actor_id=actor_id,
            reason=reason,
            details={"lead_article_id": story.lead_article_id, "initial_articles": story.article_ids},
        )
        self.audits_coll.insert_one(audit.model_dump())

        return story

    def get_story_by_id(self, story_id: str) -> Story | None:
        """Fetch story cluster by ID."""
        doc = self.stories_coll.find_one({"story_id": story_id}, {"_id": 0})
        if not doc:
            return None
        return Story.model_validate(doc)

    def get_story_for_article(self, article_id: str) -> Story | None:
        """Find the active story cluster containing this article ID."""
        doc = self.stories_coll.find_one({"article_ids": article_id}, {"_id": 0})
        if not doc:
            return None
        return Story.model_validate(doc)

    def add_article_to_story(
        self,
        story_id: str,
        article: Article,
        actor_id: str = "system_worker",
        reason: str = "event_corroboration",
    ) -> Story:
        """
        Add an article to an existing story cluster, update metrics, promote lifecycle if justified,
        increment version, and save snapshot and audit trail.
        """
        story = self.get_story_by_id(story_id)
        if not story:
            raise ValueError(f"Story '{story_id}' not found")

        if article.article_id in story.article_ids:
            return story

        art_time = article.published_at or article.fetched_at
        now = datetime.now(timezone.utc)

        new_article_ids = list(story.article_ids) + [article.article_id]
        new_sources = list(set(story.sources + [article.source_id]))
        new_article_count = len(new_article_ids)
        new_sources_count = len(new_sources)

        first_time = min(story.first_article_at, art_time)
        last_time = max(story.last_article_at, art_time)

        # Lifecycle promotion logic:
        # Multi-source coverage (>= 2 distinct sources) with multiple articles promotes to PEAK
        new_status = story.status
        peak_at = story.peak_at
        if story.status == StoryStatus.EMERGING and new_sources_count >= 2 and new_article_count >= 3:
            new_status = StoryStatus.PEAK
            peak_at = now

        new_version = story.version + 1

        update_fields: dict[str, Any] = {
            "article_ids": new_article_ids,
            "sources": new_sources,
            "article_count": new_article_count,
            "sources_count": new_sources_count,
            "first_article_at": first_time,
            "last_article_at": last_time,
            "updated_at": now,
            "status": new_status.value if isinstance(new_status, StoryStatus) else new_status,
            "peak_at": peak_at,
            "version": new_version,
        }

        self.stories_coll.update_one({"story_id": story_id}, {"$set": update_fields})

        updated_story = self.get_story_by_id(story_id)
        assert updated_story is not None

        # Snapshot
        snapshot = StorySnapshot(
            story_id=story_id,
            version=new_version,
            story_data=updated_story.model_dump(),
        )
        self.snapshots_coll.insert_one(snapshot.model_dump())

        # Audit
        audit = StoryAudit(
            story_id=story_id,
            action=StoryAuditAction.ARTICLE_ADDED,
            actor_id=actor_id,
            reason=reason,
            details={
                "article_id": article.article_id,
                "source_id": article.source_id,
                "previous_version": story.version,
                "new_version": new_version,
            },
        )
        self.audits_coll.insert_one(audit.model_dump())

        return updated_story

    def merge_stories(
        self,
        target_story_id: str,
        source_story_id: str,
        actor_id: str,
        reason: str,
    ) -> Story:
        """
        Audited manual merge of source_story into target_story.
        Combines articles, sources, entities, keywords, increments target version,
        and marks source_story as CLOSED with link to target.
        """
        if target_story_id == source_story_id:
            raise ValueError("Cannot merge a story into itself")

        target = self.get_story_by_id(target_story_id)
        if not target:
            raise ValueError(f"Target story '{target_story_id}' not found")

        source = self.get_story_by_id(source_story_id)
        if not source:
            raise ValueError(f"Source story '{source_story_id}' not found")

        now = datetime.now(timezone.utc)

        # Merge fields
        merged_article_ids = list(dict.fromkeys(target.article_ids + source.article_ids))
        merged_sources = list(dict.fromkeys(target.sources + source.sources))
        merged_entities = list(dict.fromkeys(target.entities + source.entities))
        merged_keywords = list(dict.fromkeys(target.keywords + source.keywords))

        first_time = min(target.first_article_at, source.first_article_at)
        last_time = max(target.last_article_at, source.last_article_at)

        target_new_version = target.version + 1

        target_updates = {
            "article_ids": merged_article_ids,
            "sources": merged_sources,
            "article_count": len(merged_article_ids),
            "sources_count": len(merged_sources),
            "entities": merged_entities,
            "keywords": merged_keywords,
            "first_article_at": first_time,
            "last_article_at": last_time,
            "updated_at": now,
            "version": target_new_version,
        }
        self.stories_coll.update_one({"story_id": target_story_id}, {"$set": target_updates})

        # Close source story and link to target
        source_new_version = source.version + 1
        source_updates = {
            "status": StoryStatus.CLOSED.value,
            "closed_at": now,
            "updated_at": now,
            "version": source_new_version,
            "summary": f"[Merged into story {target_story_id}] {source.summary}".strip(),
        }
        self.stories_coll.update_one({"story_id": source_story_id}, {"$set": source_updates})

        # Save snapshots
        updated_target = self.get_story_by_id(target_story_id)
        assert updated_target is not None
        self.snapshots_coll.insert_one(
            StorySnapshot(
                story_id=target_story_id,
                version=target_new_version,
                story_data=updated_target.model_dump(),
            ).model_dump()
        )

        updated_source = self.get_story_by_id(source_story_id)
        assert updated_source is not None
        self.snapshots_coll.insert_one(
            StorySnapshot(
                story_id=source_story_id,
                version=source_new_version,
                story_data=updated_source.model_dump(),
            ).model_dump()
        )

        # Audit logs on both
        self.audits_coll.insert_one(
            StoryAudit(
                story_id=target_story_id,
                action=StoryAuditAction.MERGED,
                actor_id=actor_id,
                reason=reason,
                details={
                    "merged_from_story_id": source_story_id,
                    "added_articles_count": len(source.article_ids),
                },
            ).model_dump()
        )

        self.audits_coll.insert_one(
            StoryAudit(
                story_id=source_story_id,
                action=StoryAuditAction.MERGED,
                actor_id=actor_id,
                reason=reason,
                details={"merged_into_story_id": target_story_id},
            ).model_dump()
        )

        return updated_target

    def split_story(
        self,
        source_story_id: str,
        article_ids_to_split: list[str],
        new_title: str,
        actor_id: str,
        reason: str,
    ) -> tuple[Story, Story]:
        """
        Audited manual split of specified article IDs from source_story into a brand new story.
        Preserves complete version history and audit evidence.
        """
        source = self.get_story_by_id(source_story_id)
        if not source:
            raise ValueError(f"Source story '{source_story_id}' not found")

        split_set = set(article_ids_to_split)
        remaining_articles = [aid for aid in source.article_ids if aid not in split_set]

        if not remaining_articles:
            raise ValueError("Cannot split all articles from a story; use edit or rename instead.")

        if not split_set.issubset(set(source.article_ids)):
            raise ValueError("Some specified articles do not belong to the source story.")

        now = datetime.now(timezone.utc)

        # 1. Update source story
        source_new_version = source.version + 1
        self.stories_coll.update_one(
            {"story_id": source_story_id},
            {
                "$set": {
                    "article_ids": remaining_articles,
                    "article_count": len(remaining_articles),
                    "updated_at": now,
                    "version": source_new_version,
                }
            },
        )

        updated_source = self.get_story_by_id(source_story_id)
        assert updated_source is not None

        # Snapshot for source
        self.snapshots_coll.insert_one(
            StorySnapshot(
                story_id=source_story_id,
                version=source_new_version,
                story_data=updated_source.model_dump(),
            ).model_dump()
        )

        # 2. Create new split story
        new_story_id = str(uuid.uuid4())
        new_lead = article_ids_to_split[0]
        new_story = Story(
            story_id=new_story_id,
            title=new_title,
            summary=f"انشطرت من القصة {source_story_id}: {source.title}",
            status=StoryStatus.EMERGING,
            lead_article_id=new_lead,
            article_ids=article_ids_to_split,
            sources=source.sources,
            article_count=len(article_ids_to_split),
            sources_count=len(set(source.sources)),
            first_article_at=source.first_article_at,
            last_article_at=source.last_article_at,
            created_at=now,
            updated_at=now,
            entities=source.entities,
            keywords=source.keywords,
            version=1,
        )
        self.stories_coll.insert_one(new_story.model_dump())

        # Snapshot for new story
        self.snapshots_coll.insert_one(
            StorySnapshot(
                story_id=new_story_id,
                version=1,
                story_data=new_story.model_dump(),
            ).model_dump()
        )

        # Audits for both
        self.audits_coll.insert_one(
            StoryAudit(
                story_id=source_story_id,
                action=StoryAuditAction.SPLIT,
                actor_id=actor_id,
                reason=reason,
                details={
                    "split_articles": article_ids_to_split,
                    "created_story_id": new_story_id,
                },
            ).model_dump()
        )

        self.audits_coll.insert_one(
            StoryAudit(
                story_id=new_story_id,
                action=StoryAuditAction.SPLIT,
                actor_id=actor_id,
                reason=reason,
                details={
                    "split_from_story_id": source_story_id,
                    "initial_articles": article_ids_to_split,
                },
            ).model_dump()
        )

        return updated_source, new_story

    def list_stories(
        self,
        status: StoryStatus | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, int]:
        """
        List stories with deterministic cursor pagination and short projection (Defect A12).
        Sorts by updated_at descending, story_id ascending.
        """
        filter_query: dict[str, Any] = {}
        if status:
            filter_query["status"] = status.value if isinstance(status, StoryStatus) else status

        if cursor:
            # Decode cursor format: "<iso_datetime>|<story_id>"
            parts = cursor.split("|", 1)
            if len(parts) == 2:
                try:
                    c_time = datetime.fromisoformat(parts[0])
                    c_id = parts[1]
                    cursor_cond = {
                        "$or": [
                            {"updated_at": {"$lt": c_time}},
                            {"updated_at": c_time, "story_id": {"$gt": c_id}},
                        ]
                    }
                    if filter_query:
                        filter_query = {"$and": [filter_query, cursor_cond]}
                    else:
                        filter_query = cursor_cond
                except ValueError:
                    pass

        total_count = self.stories_coll.count_documents(
            {"status": status.value} if status else {}
        )

        sort_keys = [("updated_at", DESCENDING), ("story_id", ASCENDING)]
        cursor_docs = list(
            self.stories_coll.find(filter_query, STORY_PROJECTION)
            .sort(sort_keys)
            .limit(limit + 1)
        )

        has_more = len(cursor_docs) > limit
        items = cursor_docs[:limit]

        next_cursor = None
        if has_more and items:
            last_item = items[-1]
            last_time = last_item["updated_at"]
            time_str = (
                last_time.isoformat()
                if isinstance(last_time, datetime)
                else str(last_time)
            )
            next_cursor = f"{time_str}|{last_item['story_id']}"

        return items, next_cursor, total_count

    def get_story_history(self, story_id: str) -> list[StoryAudit]:
        """Retrieve full chronological audit history for a story cluster."""
        docs = self.audits_coll.find({"story_id": story_id}, {"_id": 0}).sort(
            "timestamp", ASCENDING
        )
        return [StoryAudit.model_validate(d) for d in docs]

    def save_entity_mentions(self, mentions: list[EntityMention]) -> None:
        """Batch insert entity mentions for articles."""
        if not mentions:
            return
        docs = [m.model_dump() for m in mentions]
        self.entities_coll.insert_many(docs)

    def get_entities_for_article(self, article_id: str) -> list[EntityMention]:
        """Fetch all extracted entity mentions for an article."""
        docs = self.entities_coll.find({"article_id": article_id}, {"_id": 0})
        return [EntityMention.model_validate(d) for d in docs]
