"""Ingestion coordinator service."""

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field
from pymongo.database import Database

from insightbot.config import Settings
from insightbot.infra.fetcher import CentralFetcher
from insightbot.models.source import Source
from insightbot.modules.ingestion.discovery import DiscoveredItem, discover_from_feed
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.source_repository import SourceRepository

logger = logging.getLogger(__name__)


class IngestRunReport(BaseModel):
    """Execution summary for a bounded ingestion run."""

    source_id: str
    status: str  # 'completed', 'skipped_disabled', 'failed'
    discovered_count: int = 0
    fetched_count: int = 0
    unchanged_count: int = 0
    error_count: int = 0
    message: str = ""
    discovered_urls: list[str] = Field(default_factory=list)


class IngestionService:
    """Coordinates source ingestion, bounded crawling, and fetch audit persistence."""

    def __init__(
        self,
        db: Database[dict[str, Any]],
        settings: Settings,
        fetcher: Optional[CentralFetcher] = None,
    ):
        self.db = db
        self.settings = settings
        self.source_repo = SourceRepository(db)
        self.article_repo = ArticleRepository(db)
        self.fetches_coll = db["fetches"]
        self.fetcher = fetcher or CentralFetcher(settings)

    def ingest_source(
        self,
        source: Source,
        limit: int = 10,
        ignore_disabled: bool = False,
    ) -> IngestRunReport:
        """
        Execute bounded ingestion for a source.
        Respects disabled flag unless ignore_disabled is explicitly set for testing.
        """
        if not source.enabled and not ignore_disabled:
            logger.info("Source '%s' is disabled by policy. Skipping ingestion.", source.source_id)
            return IngestRunReport(
                source_id=source.source_id,
                status="skipped_disabled",
                message=f"Source '{source.source_id}' is disabled by policy. Enable before ingestion.",
            )

        if not source.feed_urls:
            return IngestRunReport(
                source_id=source.source_id,
                status="completed",
                message=f"Source '{source.source_id}' has no configured feed URLs.",
            )

        report = IngestRunReport(
            source_id=source.source_id,
            status="completed",
        )

        all_candidates: list[DiscoveredItem] = []

        # 1. Discover items from all feed URLs
        for feed_url in source.feed_urls:
            # Check latest fetch record for this feed URL to retrieve ETag / Last-Modified
            last_fetch = self.fetches_coll.find_one(
                {"source_id": source.source_id, "url": feed_url},
                sort=[("fetched_at", -1)],
            )
            etag = last_fetch.get("etag") if last_fetch else None
            last_modified = last_fetch.get("last_modified") if last_fetch else None

            discovered_feed, fetch_res = discover_from_feed(
                source=source,
                feed_url=feed_url,
                fetcher=self.fetcher,
                etag=etag,
                last_modified=last_modified,
            )

            # Persist audit record of feed fetch
            feed_record = self.fetcher.to_fetch_record(source.source_id, fetch_res)
            self.fetches_coll.insert_one(feed_record.model_dump())

            if discovered_feed.is_unchanged:
                report.unchanged_count += 1
            else:
                all_candidates.extend(discovered_feed.items)

        report.discovered_count = len(all_candidates)
        report.discovered_urls = [item.canonical_url for item in all_candidates[:limit]]

        # 2. Bounded fetching of candidate articles
        fetched_count = 0
        for item in all_candidates:
            if fetched_count >= limit:
                break

            # Check if canonical URL already exists in database
            self.article_repo.get_by_canonical_url(source.source_id, item.canonical_url)
            last_article_fetch = self.fetches_coll.find_one(
                {"source_id": source.source_id, "url": item.original_url},
                sort=[("fetched_at", -1)],
            )
            art_etag = last_article_fetch.get("etag") if last_article_fetch else None
            art_last_mod = last_article_fetch.get("last_modified") if last_article_fetch else None

            fetch_result = self.fetcher.fetch(
                url=item.original_url,
                source_id=source.source_id,
                etag=art_etag,
                last_modified=art_last_mod,
                allow_raw_storage=source.policy.allow_raw_storage,
            )

            # Record fetch attempt
            record = self.fetcher.to_fetch_record(source.source_id, fetch_result)
            self.fetches_coll.insert_one(record.model_dump())

            if fetch_result.is_not_modified:
                report.unchanged_count += 1
            elif fetch_result.status_code == 200:
                report.fetched_count += 1
            else:
                report.error_count += 1

            fetched_count += 1

        report.message = (
            f"Ingestion finished for '{source.source_id}': "
            f"{report.discovered_count} discovered, {report.fetched_count} fetched, "
            f"{report.unchanged_count} unchanged (304), {report.error_count} errors."
        )
        return report
