"""Repository for news sources and policy management."""

from typing import Any, Optional

from pymongo.database import Database

from insightbot.models.source import Source


class SourceRepository:
    """Repository managing news publisher sources."""

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db
        self.sources = db["sources"]

    def get_by_id(self, source_id: str) -> Optional[Source]:
        """Fetch source configuration by source_id."""
        doc = self.sources.find_one({"source_id": source_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return Source.model_validate(doc)

    def list_sources(self, enabled_only: bool = False) -> list[Source]:
        """List registered sources."""
        query = {"enabled": True} if enabled_only else {}
        cursor = self.sources.find(query).sort("source_id", 1)
        results = []
        for doc in cursor:
            doc.pop("_id", None)
            results.append(Source.model_validate(doc))
        return results

    def upsert_source(self, source: Source) -> None:
        """Insert or update a publisher source definition."""
        data = source.model_dump()
        self.sources.update_one(
            {"source_id": source.source_id},
            {"$set": data},
            upsert=True,
        )

    def set_enabled(self, source_id: str, enabled: bool) -> bool:
        """Enable or disable a source."""
        result = self.sources.update_one(
            {"source_id": source_id},
            {"$set": {"enabled": enabled}},
        )
        return result.modified_count > 0

    def get_source_health_summary(self) -> list[dict[str, Any]]:
        """
        Aggregate freshness, total articles, and failure counts per registered source.
        """
        sources = self.list_sources()
        articles_col = self.db["articles"]
        jobs_col = self.db["jobs"]

        summary: list[dict[str, Any]] = []
        for s in sources:
            art_count = articles_col.count_documents({"source_id": s.source_id})
            latest_art = articles_col.find_one(
                {"source_id": s.source_id},
                sort=[("fetched_at", -1)],
                projection={"fetched_at": 1, "published_at": 1, "_id": 0},
            )

            failed_jobs = jobs_col.count_documents({"target_id": s.source_id, "status": "failed"})
            latest_failed = jobs_col.find_one(
                {"target_id": s.source_id, "status": "failed"},
                sort=[("updated_at", -1)],
                projection={"error": 1, "updated_at": 1, "_id": 0},
            )

            summary.append(
                {
                    "source_id": s.source_id,
                    "name": s.name,
                    "url": s.url,
                    "language": s.language,
                    "enabled": s.enabled,
                    "rate_limit_per_minute": s.policy.rate_limit_per_minute,
                    "retention_days": s.policy.retention_days,
                    "total_articles": art_count,
                    "latest_fetched_at": latest_art.get("fetched_at") if latest_art else None,
                    "latest_published_at": latest_art.get("published_at") if latest_art else None,
                    "failed_jobs_count": failed_jobs,
                    "recent_error": latest_failed.get("error") if latest_failed else None,
                }
            )

        return summary
