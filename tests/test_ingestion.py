from unittest.mock import MagicMock

import mongomock
import pytest
from typer.testing import CliRunner

from insightbot.cli import app
from insightbot.config import Settings
from insightbot.infra.fetcher import CentralFetcher, FetchResult
from insightbot.models.source import Source
from insightbot.modules.ingestion.discovery import discover_from_feed
from insightbot.modules.ingestion.service import IngestionService

SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Al Jazeera News</title>
    <link>https://www.aljazeera.net</link>
    <description>Latest Arabic News</description>
    <item>
      <title>تطورات الأوضاع في الشرق الأوسط</title>
      <link>https://www.aljazeera.net/news/2026/11/16/story-1?utm_source=rss</link>
      <description>تفاصيل التقرير الإخباري الكامل.</description>
      <pubDate>Mon, 16 Nov 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".encode("utf-8")


@pytest.fixture
def mock_db_and_service(tmp_path):
    client = mongomock.MongoClient()
    db = client["test_ingest"]
    settings = Settings(
        raw_storage_path=tmp_path / "raw",
        export_storage_path=tmp_path / "exports",
    )
    fetcher = MagicMock(spec=CentralFetcher)
    service = IngestionService(db=db, settings=settings, fetcher=fetcher)
    return db, service, fetcher


def test_ingest_skips_disabled_source(mock_db_and_service):
    _, service, _ = mock_db_and_service
    disabled_source = Source(
        source_id="disabled_src",
        name="Disabled Source",
        url="https://example.com",
        feed_urls=["https://example.com/rss.xml"],
        enabled=False,
    )
    report = service.ingest_source(disabled_source, limit=5)
    assert report.status == "skipped_disabled"
    assert "disabled by policy" in report.message


def test_feed_discovery_parses_items():
    source = Source(
        source_id="aljazeera_ar",
        name="Al Jazeera Arabic",
        url="https://www.aljazeera.net",
        feed_urls=["https://www.aljazeera.net/rss.xml"],
        enabled=True,
    )
    fetcher = MagicMock(spec=CentralFetcher)
    fetcher.fetch.return_value = FetchResult(
        url="https://www.aljazeera.net/rss.xml",
        resolved_url="https://www.aljazeera.net/rss.xml",
        status_code=200,
        content_bytes=SAMPLE_RSS_XML,
        text=SAMPLE_RSS_XML.decode("utf-8"),
    )

    feed, _ = discover_from_feed(source, "https://www.aljazeera.net/rss.xml", fetcher)
    assert feed.is_unchanged is False
    assert len(feed.items) == 1
    item = feed.items[0]
    assert item.title == "تطورات الأوضاع في الشرق الأوسط"
    # Canonical URL must have stripped tracking query parameter utm_source
    assert "utm_source" not in item.canonical_url
    assert item.canonical_url == "https://www.aljazeera.net/news/2026/11/16/story-1"
    assert item.published_at is not None


def test_feed_discovery_handles_304_unchanged():
    source = Source(
        source_id="aljazeera_ar",
        name="Al Jazeera Arabic",
        url="https://www.aljazeera.net",
        feed_urls=["https://www.aljazeera.net/rss.xml"],
        enabled=True,
    )
    fetcher = MagicMock(spec=CentralFetcher)
    fetcher.fetch.return_value = FetchResult(
        url="https://www.aljazeera.net/rss.xml",
        resolved_url="https://www.aljazeera.net/rss.xml",
        status_code=304,
        is_not_modified=True,
    )

    feed, _ = discover_from_feed(source, "https://www.aljazeera.net/rss.xml", fetcher)
    assert feed.is_unchanged is True
    assert len(feed.items) == 0


def test_cli_sources_validate():
    runner = CliRunner()
    result = runner.invoke(app, ["sources", "validate", "--config", "configs/sources.yaml"])
    assert result.exit_code == 0
    assert "Source configuration is valid" in result.stdout
    assert "Registered sources: 8" in result.stdout
