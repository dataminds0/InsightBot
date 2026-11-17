"""Repository managing duplicate relationships and evidence persistence."""

import logging
from typing import Any

from pymongo.database import Database

from insightbot.models.duplicate import (
    DuplicateRelationship,
    DuplicateStatus,
    DuplicateType,
)

logger = logging.getLogger(__name__)


class DuplicateRepository:
    """Repository handling deduplication links and evidence preservation."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.collection = db["duplicate_relationships"]

    def upsert_relationship(self, rel: DuplicateRelationship) -> DuplicateRelationship:
        """Insert or update a duplicate relationship idempotently."""
        data = rel.model_dump()
        self.collection.update_one(
            {
                "canonical_article_id": rel.canonical_article_id,
                "duplicate_article_id": rel.duplicate_article_id,
            },
            {"$set": data},
            upsert=True,
        )
        return rel

    def get_relationship(
        self, canonical_id: str, duplicate_id: str
    ) -> DuplicateRelationship | None:
        """Fetch relationship between two specific articles."""
        doc = self.collection.find_one(
            {
                "canonical_article_id": canonical_id,
                "duplicate_article_id": duplicate_id,
            }
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return DuplicateRelationship.model_validate(doc)

    def get_duplicates_for_article(self, article_id: str) -> list[DuplicateRelationship]:
        """
        Find all duplicate relationships where article is either canonical or duplicate.
        """
        cursor = self.collection.find(
            {
                "$or": [
                    {"canonical_article_id": article_id},
                    {"duplicate_article_id": article_id},
                ]
            }
        ).sort("detected_at", -1)

        results: list[DuplicateRelationship] = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(DuplicateRelationship.model_validate(doc))
        return results

    def list_relationships(
        self,
        skip: int = 0,
        limit: int = 50,
        duplicate_type: DuplicateType | None = None,
        status: DuplicateStatus | None = None,
    ) -> tuple[list[DuplicateRelationship], int]:
        """List duplicate relationships with pagination and filters."""
        query: dict[str, Any] = {}
        if duplicate_type:
            query["duplicate_type"] = duplicate_type.value
        if status:
            query["status"] = status.value

        total = self.collection.count_documents(query)
        cursor = self.collection.find(query).sort("detected_at", -1).skip(skip).limit(limit)

        items: list[DuplicateRelationship] = []
        for doc in cursor:
            doc.pop("_id", None)
            items.append(DuplicateRelationship.model_validate(doc))

        return items, total

    def delete_relationship(self, relationship_id: str) -> bool:
        """Delete a duplicate relationship by its unique relationship_id."""
        res = self.collection.delete_one({"relationship_id": relationship_id})
        return res.deleted_count > 0
