"""Article repository implementing immutable version protocol and reconciliation."""

import base64
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from insightbot.models.article import Article, ArticleRevision, compute_content_hash

logger = logging.getLogger(__name__)


def encode_cursor(published_at: Optional[datetime], article_id: str) -> str:
    """Encode deterministic pagination cursor tuple."""
    iso = published_at.isoformat() if published_at else ""
    raw = json.dumps({"p": iso, "id": article_id})
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor_str: str) -> tuple[Optional[datetime], str]:
    """Decode pagination cursor tuple."""
    raw = base64.urlsafe_b64decode(cursor_str.encode("utf-8")).decode("utf-8")
    data = json.loads(raw)
    p_str = data.get("p")
    dt = datetime.fromisoformat(p_str) if p_str else None
    return dt, str(data["id"])


class ConcurrencyConflictError(Exception):
    """Raised when conditional pointer advance fails due to a fencing token or version mismatch."""

    pass


class ArticleRepository:
    """Repository handling articles and immutable revision logs."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.articles = db["articles"]
        self.versions = db["article_versions"]

    def get_by_id(self, article_id: str) -> Optional[Article]:
        """Fetch article by stable article_id."""
        doc = self.articles.find_one({"article_id": article_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return Article.model_validate(doc)

    def get_by_canonical_url(self, source_id: str, canonical_url: str) -> Optional[Article]:
        """Fetch article by source_id and canonical_url."""
        doc = self.articles.find_one({"source_id": source_id, "canonical_url": canonical_url})
        if not doc:
            return None
        doc.pop("_id", None)
        return Article.model_validate(doc)

    def get_versions(self, article_id: str) -> list[ArticleRevision]:
        """Retrieve all revision snapshots for an article ordered by version."""
        cursor = self.versions.find({"article_id": article_id}).sort("version", 1)
        revisions = []
        for doc in cursor:
            doc.pop("_id", None)
            revisions.append(ArticleRevision.model_validate(doc))
        return revisions

    def get_version_by_number(self, article_id: str, version: int) -> Optional[ArticleRevision]:
        """Fetch a specific revision snapshot by article_id and version number."""
        doc = self.versions.find_one({"article_id": article_id, "version": version})
        if not doc:
            return None
        doc.pop("_id", None)
        return ArticleRevision.model_validate(doc)

    def list_projected_articles(
        self,
        source_id: Optional[str] = None,
        language: Optional[str] = None,
        q: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_unknown_date: bool = True,
        cursor: Optional[str] = None,
        limit: int = 20,
    ) -> tuple[list[dict[str, Any]], int, Optional[str]]:
        """
        Query articles with database-level projection strictly excluding 'body_text'.
        Prevents whole-corpus memory loading (Defect A12).
        Uses deterministic cursor pagination on (published_at, article_id).
        """
        filter_clauses: list[dict[str, Any]] = []

        if source_id:
            filter_clauses.append({"source_id": source_id})
        if language:
            filter_clauses.append({"language": language})
        if q and q.strip():
            escaped_q = re.escape(q.strip())
            filter_clauses.append({"title": {"$regex": escaped_q, "$options": "i"}})

        # Date range filtering on published_at
        date_conditions: dict[str, Any] = {}
        if start_date:
            date_conditions["$gte"] = start_date
        if end_date:
            date_conditions["$lte"] = end_date

        if date_conditions:
            if include_unknown_date:
                filter_clauses.append(
                    {
                        "$or": [
                            {"published_at": date_conditions},
                            {"published_at": None},
                        ]
                    }
                )
            else:
                filter_clauses.append({"published_at": date_conditions})
        elif not include_unknown_date:
            filter_clauses.append({"published_at": {"$ne": None}})

        base_query = {"$and": filter_clauses} if filter_clauses else {}
        total_count = self.articles.count_documents(base_query)

        # Cursor pagination
        query_clauses = list(filter_clauses)
        if cursor:
            try:
                cursor_dt, cursor_id = decode_cursor(cursor)
                cursor_clause: dict[str, Any]
                if cursor_dt is not None:
                    cursor_clause = {
                        "$or": [
                            {"published_at": {"$lt": cursor_dt}},
                            {"published_at": None},
                            {"published_at": cursor_dt, "article_id": {"$gt": cursor_id}},
                        ]
                    }
                else:
                    cursor_clause = {"published_at": None, "article_id": {"$gt": cursor_id}}

                query_clauses.append(cursor_clause)
            except Exception as e:
                logger.warning("Invalid cursor '%s': %s", cursor, e)

        query = {"$and": query_clauses} if query_clauses else {}

        # STRICT PROJECTION: Exclude full body_text and internal metadata from lists!
        projection = {
            "_id": 0,
            "article_id": 1,
            "source_id": 1,
            "canonical_url": 1,
            "title": 1,
            "language": 1,
            "published_at": 1,
            "publication_date_unknown_reason": 1,
            "fetched_at": 1,
            "current_version": 1,
            "stage_states": 1,
            "quarantine_reason": 1,
            "word_count": 1,
        }

        cursor_res = (
            self.articles.find(query, projection)
            .sort([("published_at", DESCENDING), ("article_id", ASCENDING)])
            .limit(limit)
        )

        items = list(cursor_res)
        for item in items:
            wc = item.get("word_count", 0)
            item["word_count"] = wc
            item["reading_time_minutes"] = max(1, (wc + 199) // 200) if wc > 0 else 1

        next_cursor = None
        if len(items) == limit:
            last = items[-1]
            next_cursor = encode_cursor(last.get("published_at"), last["article_id"])

        return items, total_count, next_cursor

    def save_article_with_version(
        self,
        source_id: str,
        canonical_url: str,
        original_url: str,
        resolved_url: str,
        title: str,
        body_text: str,
        language: str = "ar",
        published_at: Optional[datetime] = None,
        publication_date_unknown_reason: Optional[str] = None,
        operation: str = "initial_fetch",
        raw_storage_key: Optional[str] = None,
    ) -> tuple[Article, bool]:
        """
        Store article following the immutable revision protocol.

        Returns:
            tuple[Article, bool]: (Article instance, is_new_revision_created)
        """
        now = datetime.now(timezone.utc)
        content_hash = compute_content_hash(body_text)
        word_count = len(body_text.split())

        existing = self.articles.find_one({"source_id": source_id, "canonical_url": canonical_url})

        if existing is None:
            # Brand new article
            article_id = str(uuid4())
            revision = ArticleRevision(
                article_id=article_id,
                version=1,
                title=title,
                body_text=body_text,
                content_hash=content_hash,
                operation=operation,
                created_at=now,
                raw_storage_key=raw_storage_key,
            )
            # Step 1: Persist immutable revision snapshot
            self.versions.insert_one(revision.model_dump())

            # Step 2: Persist article document pointing to version 1
            article = Article(
                article_id=article_id,
                source_id=source_id,
                canonical_url=canonical_url,
                original_url=original_url,
                resolved_url=resolved_url,
                title=title,
                body_text=body_text,
                content_hash=content_hash,
                language=language,
                published_at=published_at,
                publication_date_unknown_reason=publication_date_unknown_reason,
                fetched_at=now,
                first_seen_at=now,
                updated_at=now,
                current_version=1,
                fencing_token=1,
                word_count=word_count,
            )
            try:
                self.articles.insert_one(article.model_dump())
            except DuplicateKeyError:
                # Concurrent insert race condition: clean up revision and re-fetch
                self.versions.delete_one({"article_id": article_id, "version": 1})
                return self.save_article_with_version(
                    source_id=source_id,
                    canonical_url=canonical_url,
                    original_url=original_url,
                    resolved_url=resolved_url,
                    title=title,
                    body_text=body_text,
                    language=language,
                    published_at=published_at,
                    publication_date_unknown_reason=publication_date_unknown_reason,
                    operation=operation,
                    raw_storage_key=raw_storage_key,
                )

            return article, True

        # Existing article: check if content hash matches
        existing_hash = existing.get("content_hash")
        article_id = existing["article_id"]

        if existing_hash == content_hash:
            # Unchanged content: record fetch timestamp only, no new version
            self.articles.update_one(
                {"article_id": article_id},
                {"$set": {"fetched_at": now, "updated_at": now}},
            )
            existing["fetched_at"] = now
            existing["updated_at"] = now
            existing.pop("_id", None)
            return Article.model_validate(existing), False

        # Content has changed! Advance version atomically
        current_version = existing["current_version"]
        fencing_token = existing.get("fencing_token", 1)
        next_version = current_version + 1

        new_revision = ArticleRevision(
            article_id=article_id,
            version=next_version,
            title=title,
            body_text=body_text,
            content_hash=content_hash,
            operation=operation,
            created_at=now,
            raw_storage_key=raw_storage_key,
        )

        # Step 1: Persist new immutable revision
        self.versions.insert_one(new_revision.model_dump())

        # Step 2: Conditionally advance pointer using fencing token and expected version
        update_result = self.articles.find_one_and_update(
            {
                "article_id": article_id,
                "current_version": current_version,
                "fencing_token": fencing_token,
            },
            {
                "$set": {
                    "title": title,
                    "body_text": body_text,
                    "content_hash": content_hash,
                    "current_version": next_version,
                    "updated_at": now,
                    "fetched_at": now,
                    "word_count": word_count,
                },
                "$inc": {"fencing_token": 1},
            },
            return_document=True,
        )

        if not update_result:
            # Pointer advance conflicted; reconciliation can resolve latest revision
            raise ConcurrencyConflictError(
                f"Conflict advancing article {article_id} to version {next_version}. "
                f"Expected version {current_version} with fencing token {fencing_token}."
            )

        update_result.pop("_id", None)
        return Article.model_validate(update_result), True

    def reconcile_article_version(self, article_id: str) -> Optional[Article]:
        """
        Reconcile pointer state if a crash occurred between revision insert and pointer update.
        Never points to missing text; points to highest committed revision.
        """
        article_doc = self.articles.find_one({"article_id": article_id})
        if not article_doc:
            return None

        # Fetch all existing revisions
        revisions = list(self.versions.find({"article_id": article_id}).sort("version", 1))
        if not revisions:
            logger.warning("Article %s has zero recorded revisions.", article_id)
            return None

        latest_revision = revisions[-1]
        current_pointer = article_doc.get("current_version", 1)

        if current_pointer != latest_revision["version"]:
            logger.info(
                "Reconciling article %s: advancing pointer from %s to latest revision %s",
                article_id,
                current_pointer,
                latest_revision["version"],
            )
            self.articles.update_one(
                {"article_id": article_id},
                {
                    "$set": {
                        "title": latest_revision["title"],
                        "body_text": latest_revision["body_text"],
                        "content_hash": latest_revision["content_hash"],
                        "current_version": latest_revision["version"],
                        "updated_at": datetime.now(timezone.utc),
                    },
                    "$inc": {"fencing_token": 1},
                },
            )
            article_doc["current_version"] = latest_revision["version"]
            article_doc["title"] = latest_revision["title"]
            article_doc["body_text"] = latest_revision["body_text"]
            article_doc["content_hash"] = latest_revision["content_hash"]

        article_doc.pop("_id", None)
        return Article.model_validate(article_doc)
