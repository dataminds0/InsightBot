"""Tests for Article and Sources API endpoints, projections, cursor pagination, and security."""

from datetime import datetime, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import get_db
from insightbot.api.main import app
from insightbot.models.source import Source, SourcePolicy
from insightbot.models.user import Role, UserStatus
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.source_repository import SourceRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthService


@pytest.fixture
def article_api_env():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_article_api"]

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    # Setup user and auth token
    user_repo = UserRepository(mock_db)
    auth_service = AuthService(user_repo)
    auth_service.register(
        "viewer_user", "ViewerSecret123", role=Role.VIEWER, status=UserStatus.ACTIVE
    )
    _, session = auth_service.login("viewer_user", "ViewerSecret123")
    token = session.session_token

    # Setup sources
    source_repo = SourceRepository(mock_db)
    s1 = Source(
        source_id="aljazeera_ar",
        name="الجزيرة",
        url="https://aljazeera.net",
        language="ar",
        enabled=True,
        policy=SourcePolicy(rate_limit_per_minute=20),
    )
    s2 = Source(
        source_id="reuters_en",
        name="Reuters",
        url="https://reuters.com",
        language="en",
        enabled=False,
        policy=SourcePolicy(rate_limit_per_minute=30),
    )
    source_repo.upsert_source(s1)
    source_repo.upsert_source(s2)

    # Setup articles
    article_repo = ArticleRepository(mock_db)
    dt1 = datetime(2026, 11, 10, 10, 0, 0, tzinfo=timezone.utc)
    dt2 = datetime(2026, 11, 12, 15, 30, 0, tzinfo=timezone.utc)

    # Article 1: Arabic with published_at dt1
    art1, _ = article_repo.save_article_with_version(
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/news/gaza-developments",
        original_url="https://aljazeera.net/news/gaza-developments",
        resolved_url="https://aljazeera.net/news/gaza-developments",
        title="غزة: تطورات ميدانية وإنسانية",
        body_text="هذا هو النص الكامل للتقرير الإخباري الذي يحتوي على تفاصيل دقيقة وسرية.",
        language="ar",
        published_at=dt1,
        operation="initial_fetch",
    )

    # Update Article 1 to generate version 2
    art1_v2, _ = article_repo.save_article_with_version(
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/news/gaza-developments",
        original_url="https://aljazeera.net/news/gaza-developments",
        resolved_url="https://aljazeera.net/news/gaza-developments",
        title="غزة: تطورات ميدانية وإنسانية (محدث)",
        body_text="النص الكامل للنسخة الثانية مع إضافات صحفية وتحديثات جديدة.",
        language="ar",
        published_at=dt1,
        operation="editor_update",
    )

    # Article 2: Arabic with published_at dt2
    art2, _ = article_repo.save_article_with_version(
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/news/economy-inflation",
        original_url="https://aljazeera.net/news/economy-inflation",
        resolved_url="https://aljazeera.net/news/economy-inflation",
        title="تقرير: التضخم وأسعار الفائدة في المنطقة",
        body_text="نص تقرير اقتصادي مفصل عن التضخم.",
        language="ar",
        published_at=dt2,
        operation="initial_fetch",
    )

    # Article 3: English with unknown date
    art3, _ = article_repo.save_article_with_version(
        source_id="reuters_en",
        canonical_url="https://reuters.com/markets/tech-rally",
        original_url="https://reuters.com/markets/tech-rally",
        resolved_url="https://reuters.com/markets/tech-rally",
        title="Tech stocks rally on artificial intelligence momentum",
        body_text="Full English body text analyzing Wall Street rally.",
        language="en",
        published_at=None,
        publication_date_unknown_reason="missing_in_feed_and_metadata",
        operation="initial_fetch",
    )

    yield client, token, [art1_v2, art2, art3]
    app.dependency_overrides.clear()


def test_articles_api_requires_authentication(article_api_env):
    client, _, _ = article_api_env
    resp = client.get("/api/articles")
    assert resp.status_code == 401
    assert "detail" in resp.json()
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_articles_list_projection_strictly_excludes_body_text(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/articles", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "items" in data
    assert len(data["items"]) == 3
    assert data["total_count"] == 3

    # CRITICAL SECURITY / A12 GATE: No body_text in ANY list item!
    for item in data["items"]:
        assert "body_text" not in item, "body_text leaked in article list item!"
        assert "article_id" in item
        assert "title" in item
        assert "source_id" in item
        assert "canonical_url" in item


def test_articles_list_filtering_by_source_and_language(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}

    # Filter by source_id
    resp = client.get("/api/articles?source_id=reuters_en", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["source_id"] == "reuters_en"
    assert items[0]["language"] == "en"

    # Filter by language
    resp_ar = client.get("/api/articles?language=ar", headers=headers)
    assert resp_ar.status_code == 200
    ar_items = resp_ar.json()["items"]
    assert len(ar_items) == 2
    for item in ar_items:
        assert item["language"] == "ar"


def test_articles_list_search_by_keyword(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}

    # Arabic keyword search
    resp = client.get("/api/articles?q=غزة", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert "غزة" in items[0]["title"]

    # English keyword search
    resp_en = client.get("/api/articles?q=stocks", headers=headers)
    assert resp_en.status_code == 200
    items_en = resp_en.json()["items"]
    assert len(items_en) == 1
    assert "stocks" in items_en[0]["title"]


def test_articles_list_date_filtering_and_unknown_dates(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}

    # Exclude unknown dates
    resp = client.get("/api/articles?include_unknown_date=false", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    for item in items:
        assert item["published_at"] is not None

    # Date range window: 2026-11-11 to 2026-11-13 (matches only dt2 = 2026-11-12)
    start = "2026-11-11T00:00:00Z"
    end = "2026-11-13T00:00:00Z"
    resp_range = client.get(
        f"/api/articles?start_date={start}&end_date={end}&include_unknown_date=false",
        headers=headers,
    )
    assert resp_range.status_code == 200
    range_items = resp_range.json()["items"]
    assert len(range_items) == 1
    assert range_items[0]["title"] == "تقرير: التضخم وأسعار الفائدة في المنطقة"


def test_articles_cursor_pagination(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}

    # Page 1: limit 2
    resp_p1 = client.get("/api/articles?limit=2", headers=headers)
    assert resp_p1.status_code == 200
    data_p1 = resp_p1.json()
    assert len(data_p1["items"]) == 2
    next_cursor = data_p1["next_cursor"]
    assert next_cursor is not None

    # Page 2: with cursor
    resp_p2 = client.get(f"/api/articles?limit=2&cursor={next_cursor}", headers=headers)
    assert resp_p2.status_code == 200
    data_p2 = resp_p2.json()
    assert len(data_p2["items"]) == 1

    # Verify no overlapping items
    p1_ids = {item["article_id"] for item in data_p1["items"]}
    p2_ids = {item["article_id"] for item in data_p2["items"]}
    assert p1_ids.isdisjoint(p2_ids)


def test_articles_limit_validation(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}

    # limit > 100 must fail with 422 validation error
    resp = client.get("/api/articles?limit=101", headers=headers)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_article_detail_includes_full_body_text(article_api_env):
    client, token, articles = article_api_env
    headers = {"Authorization": f"Bearer {token}"}
    art = articles[0]

    resp = client.get(f"/api/articles/{art.article_id}", headers=headers)
    assert resp.status_code == 200
    detail = resp.json()

    assert detail["article_id"] == art.article_id
    assert "body_text" in detail
    assert detail["body_text"] == "النص الكامل للنسخة الثانية مع إضافات صحفية وتحديثات جديدة."
    assert detail["current_version"] == 2
    assert detail["canonical_url"] == art.canonical_url


def test_article_detail_not_found(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/articles/nonexistent-uuid", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    assert "nonexistent-uuid" in resp.json()["error"]["message"]


def test_article_versions_history(article_api_env):
    client, token, articles = article_api_env
    headers = {"Authorization": f"Bearer {token}"}
    art = articles[0]  # has 2 versions

    # All versions
    resp = client.get(f"/api/articles/{art.article_id}/versions", headers=headers)
    assert resp.status_code == 200
    versions = resp.json()
    assert len(versions) == 2
    assert versions[0]["version"] == 1
    assert "سرية" in versions[0]["body_text"]
    assert versions[1]["version"] == 2
    assert "وتحديثات جديدة" in versions[1]["body_text"]

    # Specific version snapshot
    resp_v1 = client.get(f"/api/articles/{art.article_id}/versions/1", headers=headers)
    assert resp_v1.status_code == 200
    assert resp_v1.json()["version"] == 1
    assert resp_v1.json()["operation"] == "initial_fetch"

    # Non-existent version
    resp_v99 = client.get(f"/api/articles/{art.article_id}/versions/99", headers=headers)
    assert resp_v99.status_code == 404
    assert resp_v99.json()["error"]["code"] == "NOT_FOUND"


def test_sources_api(article_api_env):
    client, token, _ = article_api_env
    headers = {"Authorization": f"Bearer {token}"}

    # List all sources
    resp = client.get("/api/sources", headers=headers)
    assert resp.status_code == 200
    sources = resp.json()
    assert len(sources) == 2

    # Filter enabled only
    resp_enabled = client.get("/api/sources?enabled_only=true", headers=headers)
    assert resp_enabled.status_code == 200
    enabled_sources = resp_enabled.json()
    assert len(enabled_sources) == 1
    assert enabled_sources[0]["source_id"] == "aljazeera_ar"

    # Detail of specific source
    resp_detail = client.get("/api/sources/aljazeera_ar", headers=headers)
    assert resp_detail.status_code == 200
    assert resp_detail.json()["source_id"] == "aljazeera_ar"
    assert resp_detail.json()["policy"]["rate_limit_per_minute"] == 20

    # Non-existent source
    resp_404 = client.get("/api/sources/nonexistent_source", headers=headers)
    assert resp_404.status_code == 404
    assert resp_404.json()["error"]["code"] == "NOT_FOUND"


def test_middleware_request_id_and_capabilities(article_api_env):
    client, token, _ = article_api_env

    # Custom X-Request-ID echo
    custom_id = "test-req-id-12345"
    resp = client.get("/api/health", headers={"X-Request-ID": custom_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_id

    # Auto-generated X-Request-ID
    resp_auto = client.get("/api/health")
    assert resp_auto.status_code == 200
    assert "X-Request-ID" in resp_auto.headers
    assert len(resp_auto.headers["X-Request-ID"]) > 0

    # Capabilities endpoint
    resp_caps = client.get("/api/capabilities")
    assert resp_caps.status_code == 200
    caps = resp_caps.json()
    assert caps["version"] == "0.1.0"
    assert "ar" in caps["languages"]
    assert "ar" in caps["rtl_languages"]
    assert caps["max_page_limit"] == 100
