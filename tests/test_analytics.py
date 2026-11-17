"""Comprehensive unit and API tests for Analytics overview, metrics reconciliation, and CSV formula protection."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import (
    get_analytics_service,
    get_current_user,
    get_db,
    get_export_service,
)
from insightbot.api.main import app
from insightbot.models.article import Article, compute_content_hash
from insightbot.models.export import ExportFormat
from insightbot.models.source import Source
from insightbot.models.story import Story, StoryStatus
from insightbot.models.user import Role, User
from insightbot.modules.analytics.export import ExportService, sanitize_csv_cell
from insightbot.modules.analytics.service import AnalyticsService


@pytest.fixture
def mock_db() -> Any:
    """In-memory mongomock database fixture."""
    client: Any = mongomock.MongoClient()
    return client["insightbot_test_analytics"]


@pytest.fixture
def seeded_db(mock_db: Any) -> Any:
    """Seeds articles, sources, and stories for analytics reconciliation."""
    t0 = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=30)

    # 1. Sources
    s1 = Source(source_id="aljazeera_ar", name="الجزيرة", url="https://aljazeera.net", language="ar")
    s2 = Source(source_id="reuters_en", name="Reuters", url="https://reuters.com", language="en")
    mock_db["sources"].insert_many([s1.model_dump(), s2.model_dump()])

    # 2. Articles (including one with formula injection attempt and one with unknown pub date)
    body1 = "تقرير إخباري حول مؤشرات الاقتصاد العالمي والتضخم."
    a1 = Article(
        article_id="art-1",
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/econ",
        original_url="https://aljazeera.net/econ",
        resolved_url="https://aljazeera.net/econ",
        title="=cmd|' /C calc'!A0",  # CSV FORMULA INJECTION VECTOR!
        body_text=body1,
        content_hash=compute_content_hash(body1),
        language="ar",
        published_at=t0,
        fetched_at=t0 + timedelta(minutes=20),  # 20 min lag
        word_count=120,
        reading_time_minutes=1,
    )

    body2 = "Global markets trade higher amid corporate earnings optimism."
    a2 = Article(
        article_id="art-2",
        source_id="reuters_en",
        canonical_url="https://reuters.com/markets",
        original_url="https://reuters.com/markets",
        resolved_url="https://reuters.com/markets",
        title="+SUM(1+1)*2",  # FORMULA INJECTION VECTOR 2
        body_text=body2,
        content_hash=compute_content_hash(body2),
        language="en",
        published_at=None,  # DEFECT A13: UNKNOWN PUBLICATION DATE
        publication_date_unknown_reason="RSS feed omitted pubDate",
        fetched_at=t1,
        word_count=240,
        reading_time_minutes=2,
    )

    mock_db["articles"].insert_many([a1.model_dump(), a2.model_dump()])

    # 3. Story
    story = Story(
        story_id="story-econ-1",
        title="متابعة مؤشرات الأسواق والتضخم",
        status=StoryStatus.EMERGING,
        lead_article_id="art-1",
        article_ids=["art-1", "art-2"],
        sources=["aljazeera_ar", "reuters_en"],
        article_count=2,
        sources_count=2,
        first_article_at=t0,
        last_article_at=t1,
    )
    mock_db["stories"].insert_one(story.model_dump())

    return mock_db


def test_sanitize_csv_cell_formula_protection() -> None:
    """Verify CWE-1236 CSV Formula Injection defense on all dangerous prefixes."""
    # Dangerous formula prefixes must be neutralized with a single quote prefix
    assert sanitize_csv_cell("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert sanitize_csv_cell("+12345") == "'+12345"
    assert sanitize_csv_cell("-100") == "'-100"
    assert sanitize_csv_cell("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_cell("\tTabbed") == "'\tTabbed"
    assert sanitize_csv_cell("\rReturn") == "'\rReturn"
    assert sanitize_csv_cell("%50") == "'%50"

    # Benign text must remain unchanged
    assert sanitize_csv_cell("تقرير اقتصادي عادي") == "تقرير اقتصادي عادي"
    assert sanitize_csv_cell("Al Jazeera News") == "Al Jazeera News"
    assert sanitize_csv_cell(None) == ""
    assert sanitize_csv_cell(123) == "123"


def test_analytics_overview_reconciliation(seeded_db: Any) -> None:
    """Verify that metrics reconcile with underlying articles, sources, and stories."""
    service = AnalyticsService(seeded_db)
    report = service.get_overview_report()

    assert report.total_articles == 2
    assert report.total_sources == 2
    assert report.total_stories == 1

    # Defect A13 visible metric: exactly 1 article has unknown pub date
    assert report.unknown_publication_date_count == 1

    # Language distribution
    lang_map = {item.language: item.count for item in report.language_distribution}
    assert lang_map["ar"] == 1
    assert lang_map["en"] == 1

    # Source coverage
    coverage_map = {item.source_id: item for item in report.source_coverage}
    assert "aljazeera_ar" in coverage_map
    assert coverage_map["aljazeera_ar"].article_count == 1
    assert coverage_map["aljazeera_ar"].publishing_lag_minutes == 20.0  # 20 min lag


def test_export_articles_csv_jsonl_markdown(seeded_db: Any) -> None:
    """Verify CSV, JSONL, and Markdown export outputs and manifest generation."""
    service = ExportService(seeded_db)

    # 1. CSV with formula injection defense
    csv_content, media_type, manifest = service.export_articles(ExportFormat.CSV)
    assert media_type == "text/csv; charset=utf-8"
    assert manifest.total_exported == 2
    assert manifest.formula_protection_applied is True
    # Verify the formula injection titles are sanitized in the output
    assert "'=cmd|' /C calc'!A0" in csv_content
    assert "'+SUM(1+1)*2" in csv_content

    # 2. JSONL export
    jsonl_content, jsonl_media, _ = service.export_articles(ExportFormat.JSONL)
    assert jsonl_media == "application/x-ndjson; charset=utf-8"
    lines = [line for line in jsonl_content.strip().split("\n") if line]
    assert len(lines) == 2
    doc1 = json.loads(lines[0])
    assert doc1["article_id"] in ["art-1", "art-2"]

    # 3. Markdown export
    md_content, md_media, _ = service.export_articles(ExportFormat.MARKDOWN)
    assert md_media == "text/markdown; charset=utf-8"
    assert "| المعرف | المصدر | اللغة | تاريخ النشر |" in md_content
    assert "`art-1`" in md_content
    assert "`art-2`" in md_content


def test_export_stories(seeded_db: Any) -> None:
    """Verify story cluster export in CSV format."""
    service = ExportService(seeded_db)
    csv_content, _, manifest = service.export_stories(ExportFormat.CSV)

    assert manifest.total_exported == 1
    assert "story-econ-1" in csv_content
    assert "aljazeera_ar, reuters_en" in csv_content


def test_analytics_and_export_api_endpoints(seeded_db: Any) -> None:
    """Verify GET /api/analytics/overview and GET /api/export/articles endpoints."""
    client = TestClient(app)

    # 1. Unauthenticated gets 401
    res_unauth = client.get("/api/analytics/overview")
    assert res_unauth.status_code == 401

    # Override dependencies
    viewer_user = User(user_id="viewer-1", username="viewer", role=Role.VIEWER, password_hash="dummy")
    app.dependency_overrides[get_db] = lambda: seeded_db
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    app.dependency_overrides[get_analytics_service] = lambda: AnalyticsService(seeded_db)
    app.dependency_overrides[get_export_service] = lambda: ExportService(seeded_db)

    # 2. Authenticated overview
    res_overview = client.get("/api/analytics/overview")
    assert res_overview.status_code == 200
    data = res_overview.json()
    assert data["total_articles"] == 2
    assert data["unknown_publication_date_count"] == 1
    assert len(data["source_coverage"]) == 2

    # 3. Export CSV articles endpoint
    res_export = client.get("/api/export/articles?format=csv")
    assert res_export.status_code == 200
    assert "text/csv" in res_export.headers["content-type"]
    assert "attachment; filename=\"insightbot_articles_" in res_export.headers["content-disposition"]
    assert res_export.headers["x-export-count"] == "2"
    assert "'=cmd|' /C calc'!A0" in res_export.text

    # 4. Export Stories endpoint
    res_exp_stories = client.get("/api/export/stories?format=csv")
    assert res_exp_stories.status_code == 200
    assert "insightbot_stories_" in res_exp_stories.headers["content-disposition"]

    app.dependency_overrides.clear()
