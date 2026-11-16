"""Personal workspace repository managing bookmarks, saved queries, and notes."""

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from insightbot.models.workspace import Bookmark, PrivateNote, SavedQuery

logger = logging.getLogger(__name__)

ARTICLE_PROJECTION: dict[str, int] = {
    "_id": 0,
    "article_id": 1,
    "title": 1,
    "source_id": 1,
    "published_at": 1,
    "canonical_url": 1,
    "language": 1,
    "reading_time_minutes": 1,
    "word_count": 1,
    "unknown_date": 1,
    "published_at_raw": 1,
}


class WorkspaceRepository:
    """Repository handling owner-isolated bookmarks, saved queries, and analytical notes."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.bookmarks = db["bookmarks"]
        self.saved_queries = db["saved_queries"]
        self.notes = db["private_notes"]
        self.articles = db["articles"]

    # --- Bookmarks ---

    def add_bookmark(
        self,
        user_id: str,
        article_id: str,
        notes: str | None = None,
        tags: list[str] | None = None,
    ) -> Bookmark:
        """Create or update a bookmark for an article."""
        cleaned_tags = [t.strip() for t in (tags or []) if t.strip()]
        existing = self.bookmarks.find_one({"user_id": user_id, "article_id": article_id})
        if existing:
            self.bookmarks.update_one(
                {"_id": existing["_id"]},
                {"$set": {"notes": notes, "tags": cleaned_tags}},
            )
            existing["notes"] = notes
            existing["tags"] = cleaned_tags
            existing.pop("_id", None)
            return Bookmark.model_validate(existing)

        bookmark = Bookmark(
            user_id=user_id,
            article_id=article_id,
            notes=notes,
            tags=cleaned_tags,
        )
        self.bookmarks.insert_one(bookmark.model_dump())
        return bookmark

    def remove_bookmark(self, user_id: str, article_id: str) -> bool:
        """Remove a bookmark for a specific user and article."""
        res = self.bookmarks.delete_one({"user_id": user_id, "article_id": article_id})
        return res.deleted_count > 0

    def is_bookmarked(self, user_id: str, article_id: str) -> bool:
        """Check whether an article is bookmarked by user."""
        return (
            self.bookmarks.find_one({"user_id": user_id, "article_id": article_id}, {"_id": 1})
            is not None
        )

    def get_bookmark(self, user_id: str, article_id: str) -> Bookmark | None:
        """Get bookmark details for a specific article and user."""
        doc = self.bookmarks.find_one({"user_id": user_id, "article_id": article_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return Bookmark.model_validate(doc)

    def list_bookmarks(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        tag: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List bookmarks for user with target article preview and availability status."""
        query: dict[str, Any] = {"user_id": user_id}
        if tag:
            query["tags"] = tag.strip()

        total = self.bookmarks.count_documents(query)
        cursor = self.bookmarks.find(query).sort("created_at", -1).skip(skip).limit(limit)

        results: list[dict[str, Any]] = []
        for doc in cursor:
            doc.pop("_id", None)
            article_id = doc["article_id"]
            article_doc = self.articles.find_one({"article_id": article_id}, ARTICLE_PROJECTION)

            results.append(
                {
                    "bookmark_id": doc["bookmark_id"],
                    "user_id": doc["user_id"],
                    "article_id": article_id,
                    "notes": doc.get("notes"),
                    "tags": doc.get("tags", []),
                    "created_at": doc["created_at"],
                    "target_available": article_doc is not None,
                    "article": article_doc,
                }
            )

        return results, total

    # --- Saved Queries ---

    def save_query(
        self,
        user_id: str,
        name: str,
        query_params: dict[str, Any],
        alerts_enabled: bool = False,
    ) -> SavedQuery:
        """Save a search query and filter set."""
        saved_query = SavedQuery(
            user_id=user_id,
            name=name.strip(),
            query_params=query_params,
            alerts_enabled=alerts_enabled,
        )
        self.saved_queries.insert_one(saved_query.model_dump())
        return saved_query

    def get_query(self, user_id: str, query_id: str) -> SavedQuery | None:
        """Fetch a saved query ensuring strict owner isolation."""
        doc = self.saved_queries.find_one({"query_id": query_id, "user_id": user_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return SavedQuery.model_validate(doc)

    def list_queries(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[SavedQuery], int]:
        """List saved queries owned by user."""
        query = {"user_id": user_id}
        total = self.saved_queries.count_documents(query)
        cursor = self.saved_queries.find(query).sort("created_at", -1).skip(skip).limit(limit)

        items: list[SavedQuery] = []
        for doc in cursor:
            doc.pop("_id", None)
            items.append(SavedQuery.model_validate(doc))

        return items, total

    def delete_query(self, user_id: str, query_id: str) -> bool:
        """Delete a saved query ensuring strict owner isolation."""
        res = self.saved_queries.delete_one({"query_id": query_id, "user_id": user_id})
        return res.deleted_count > 0

    # --- Private Notes ---

    def upsert_note(self, user_id: str, article_id: str, content: str) -> PrivateNote:
        """Create or update a private analytical note on an article."""
        now = datetime.now(timezone.utc)
        existing = self.notes.find_one({"user_id": user_id, "article_id": article_id})
        if existing:
            self.notes.update_one(
                {"_id": existing["_id"]},
                {"$set": {"content": content, "updated_at": now}},
            )
            existing["content"] = content
            existing["updated_at"] = now
            existing.pop("_id", None)
            return PrivateNote.model_validate(existing)

        note = PrivateNote(
            user_id=user_id,
            article_id=article_id,
            content=content,
            created_at=now,
            updated_at=now,
        )
        self.notes.insert_one(note.model_dump())
        return note

    def get_note(self, user_id: str, article_id: str) -> PrivateNote | None:
        """Get private note for an article ensuring strict owner isolation."""
        doc = self.notes.find_one({"user_id": user_id, "article_id": article_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return PrivateNote.model_validate(doc)

    def delete_note(self, user_id: str, article_id: str) -> bool:
        """Delete a private note ensuring strict owner isolation."""
        res = self.notes.delete_one({"user_id": user_id, "article_id": article_id})
        return res.deleted_count > 0

    def list_notes(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """List private notes with target article preview."""
        query = {"user_id": user_id}
        total = self.notes.count_documents(query)
        cursor = self.notes.find(query).sort("updated_at", -1).skip(skip).limit(limit)

        results: list[dict[str, Any]] = []
        for doc in cursor:
            doc.pop("_id", None)
            article_id = doc["article_id"]
            article_doc = self.articles.find_one({"article_id": article_id}, ARTICLE_PROJECTION)

            results.append(
                {
                    "note_id": doc["note_id"],
                    "user_id": doc["user_id"],
                    "article_id": article_id,
                    "content": doc["content"],
                    "created_at": doc["created_at"],
                    "updated_at": doc["updated_at"],
                    "target_available": article_doc is not None,
                    "article": article_doc,
                }
            )

        return results, total
