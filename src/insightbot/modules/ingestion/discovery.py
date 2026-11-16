"""Feed item discovery from RSS and Atom feeds."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import feedparser
from pydantic import BaseModel, Field

from insightbot.infra.fetcher import CentralFetcher, FetchResult
from insightbot.models.source import Source
from insightbot.modules.ingestion.url import normalize_canonical_url

logger = logging.getLogger(__name__)


class DiscoveredItem(BaseModel):
    """Article candidate item discovered from feed or listing."""

    source_id: str
    original_url: str
    canonical_url: str
    title: str
    published_at: Optional[datetime] = None
    summary_hint: Optional[str] = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DiscoveredFeed(BaseModel):
    """Result of feed discovery check."""

    source_id: str
    feed_url: str
    is_unchanged: bool = False
    items: list[DiscoveredItem] = Field(default_factory=list)


def parse_feed_datetime(entry: feedparser.FeedParserDict) -> Optional[datetime]:
    """Extract and parse publication date from feed entry as UTC datetime."""
    parsed_struct = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if parsed_struct:
        try:
            timestamp = time.mktime(parsed_struct)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except Exception:
            pass
    return None


def discover_from_feed(
    source: Source,
    feed_url: str,
    fetcher: CentralFetcher,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> tuple[DiscoveredFeed, FetchResult]:
    """
    Fetch and parse an RSS/Atom feed using conditional request headers.
    If the server returns 304 Not Modified, returns is_unchanged=True without refetching history.
    """
    fetch_res = fetcher.fetch(
        url=feed_url,
        source_id=source.source_id,
        etag=etag,
        last_modified=last_modified,
        allow_raw_storage=False,  # We don't need to persist raw feed index XML indefinitely
    )

    if fetch_res.is_not_modified or fetch_res.status_code == 304:
        logger.info(
            "Feed '%s' for source '%s' returned 304 Not Modified. No new items.",
            feed_url,
            source.source_id,
        )
        return (
            DiscoveredFeed(
                source_id=source.source_id,
                feed_url=feed_url,
                is_unchanged=True,
                items=[],
            ),
            fetch_res,
        )

    if fetch_res.status_code != 200 or not fetch_res.content_bytes:
        logger.warning(
            "Feed '%s' returned status %d. Error: %s",
            feed_url,
            fetch_res.status_code,
            fetch_res.error,
        )
        return (
            DiscoveredFeed(
                source_id=source.source_id,
                feed_url=feed_url,
                is_unchanged=False,
                items=[],
            ),
            fetch_res,
        )

    # Parse feed bytes safely
    parsed_feed = feedparser.parse(fetch_res.content_bytes)
    discovered_items: list[DiscoveredItem] = []

    for entry in parsed_feed.entries:
        link = getattr(entry, "link", None)
        if not link or not isinstance(link, str) or not link.strip():
            continue

        raw_link = link.strip()
        try:
            canonical = normalize_canonical_url(raw_link)
        except Exception:
            canonical = raw_link

        title = getattr(entry, "title", "").strip()
        published_at = parse_feed_datetime(entry)
        summary = getattr(entry, "summary", None) or getattr(entry, "description", None)

        discovered_items.append(
            DiscoveredItem(
                source_id=source.source_id,
                original_url=raw_link,
                canonical_url=canonical,
                title=title,
                published_at=published_at,
                summary_hint=summary.strip() if summary else None,
            )
        )

    logger.info("Discovered %d candidate items from feed '%s'", len(discovered_items), feed_url)
    return (
        DiscoveredFeed(
            source_id=source.source_id,
            feed_url=feed_url,
            is_unchanged=False,
            items=discovered_items,
        ),
        fetch_res,
    )
