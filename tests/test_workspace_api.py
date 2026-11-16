"""Tests for Personal Workspace: Bookmarks, Saved Queries, Notes, and Cross-User Isolation."""

from datetime import datetime, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import get_db
from insightbot.api.main import app
from insightbot.models.user import Role, UserStatus
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthService


@pytest.fixture
def workspace_env():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_workspace"]

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    user_repo = UserRepository(mock_db)
    auth_service = AuthService(user_repo)

    # User 1: Analyst Alpha
    analyst_a = auth_service.register(
        "analyst_alpha", "PasswordAlpha123!", role=Role.ANALYST, status=UserStatus.ACTIVE
    )
    # User 2: Analyst Beta
    analyst_b = auth_service.register(
        "analyst_beta", "PasswordBeta123!", role=Role.ANALYST, status=UserStatus.ACTIVE
    )
    # User 3: Viewer
    auth_service.register(
        "viewer_charlie", "PasswordCharlie123!", role=Role.VIEWER, status=UserStatus.ACTIVE
    )

    _, session_a = auth_service.login("analyst_alpha", "PasswordAlpha123!")
    _, session_b = auth_service.login("analyst_beta", "PasswordBeta123!")
    _, session_v = auth_service.login("viewer_charlie", "PasswordCharlie123!")

    token_a = session_a.session_token
    token_b = session_b.session_token
    token_v = session_v.session_token

    # Pre-seed sample articles
    article_repo = ArticleRepository(mock_db)
    text_1 = "محتوى المقال الأول..."
    art1, _ = article_repo.save_article_with_version(
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/news/art-100",
        original_url="https://aljazeera.net/news/art-100",
        resolved_url="https://aljazeera.net/news/art-100",
        title="مقال تحليلي أول",
        body_text=text_1,
        language="ar",
        published_at=datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc),
    )

    text_2 = "محتوى المقال الثاني..."
    art2, _ = article_repo.save_article_with_version(
        source_id="bbc_ar",
        canonical_url="https://bbc.com/arabic/art-200",
        original_url="https://bbc.com/arabic/art-200",
        resolved_url="https://bbc.com/arabic/art-200",
        title="مقال تجريبي ثان",
        body_text=text_2,
        language="ar",
        published_at=datetime(2026, 11, 16, 11, 0, tzinfo=timezone.utc),
    )

    article_1_id = art1.article_id
    article_2_id = art2.article_id

    yield {
        "client": client,
        "token_a": token_a,
        "user_a": analyst_a,
        "token_b": token_b,
        "user_b": analyst_b,
        "token_v": token_v,
        "mock_db": mock_db,
        "article_1_id": article_1_id,
        "article_2_id": article_2_id,
    }

    app.dependency_overrides.clear()


def test_viewer_access_denied(workspace_env):
    """Viewers are forbidden from modifying or accessing workspace resources."""
    client = workspace_env["client"]
    token_v = workspace_env["token_v"]
    headers = {"Authorization": f"Bearer {token_v}"}

    res = client.get("/api/workspace/bookmarks", headers=headers)
    assert res.status_code == 403

    res = client.get("/api/workspace/queries", headers=headers)
    assert res.status_code == 403

    res = client.get("/api/workspace/notes", headers=headers)
    assert res.status_code == 403


def test_bookmarks_lifecycle_and_target_availability(workspace_env):
    """Test bookmarking, updating tags/notes, listing with target info, and missing targets."""
    client = workspace_env["client"]
    token_a = workspace_env["token_a"]
    art1_id = workspace_env["article_1_id"]
    headers = {"Authorization": f"Bearer {token_a}"}

    # 1. Check status before bookmarking
    status_res = client.get(f"/api/workspace/bookmarks/status/{art1_id}", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["is_bookmarked"] is False

    # 2. Add bookmark
    create_res = client.post(
        "/api/workspace/bookmarks",
        json={"article_id": art1_id, "notes": "ملاحظة هامة", "tags": ["عاجل", "سياسة"]},
        headers=headers,
    )
    assert create_res.status_code == 201
    bm_data = create_res.json()
    assert bm_data["article_id"] == art1_id
    assert bm_data["tags"] == ["عاجل", "سياسة"]

    # 3. Check status after bookmarking
    status_res = client.get(f"/api/workspace/bookmarks/status/{art1_id}", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["is_bookmarked"] is True

    # 4. Bookmark a non-existent article (unavailable target scenario)
    fake_id = "art-missing-999"
    client.post(
        "/api/workspace/bookmarks",
        json={"article_id": fake_id, "notes": "مقال محذوف"},
        headers=headers,
    )

    # 5. List bookmarks: verifies pagination and unavailable target handling
    list_res = client.get("/api/workspace/bookmarks", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Verify existing target item
    art_100_item = next(it for it in data["items"] if it["article_id"] == art1_id)
    assert art_100_item["target_available"] is True
    assert art_100_item["article"] is not None
    assert art_100_item["article"]["title"] == "مقال تحليلي أول"
    # Defect A12 protection: body_text is never projected in bookmark listing
    assert "body_text" not in art_100_item["article"]

    # Verify unavailable target item
    missing_item = next(it for it in data["items"] if it["article_id"] == fake_id)
    assert missing_item["target_available"] is False
    assert missing_item["article"] is None

    # 6. Filter by tag
    tag_res = client.get("/api/workspace/bookmarks?tag=عاجل", headers=headers)
    assert tag_res.status_code == 200
    assert tag_res.json()["total"] == 1
    assert tag_res.json()["items"][0]["article_id"] == art1_id

    # 7. Delete bookmark
    del_res = client.delete(f"/api/workspace/bookmarks/{art1_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    # Deleting again returns 404
    del_res_again = client.delete(f"/api/workspace/bookmarks/{art1_id}", headers=headers)
    assert del_res_again.status_code == 404


def test_saved_queries_and_alerts_flag(workspace_env):
    """Test saving search parameters, listing, and alert delivery notification."""
    client = workspace_env["client"]
    token_a = workspace_env["token_a"]
    headers = {"Authorization": f"Bearer {token_a}"}

    query_payload = {
        "name": "متابعة الشرق الأوسط",
        "query_params": {
            "q": "الشرق الأوسط",
            "source_id": "aljazeera_ar",
            "language": "ar",
            "include_unknown_date": True,
        },
        "alerts_enabled": True,  # Will be flagged as disabled until T19
    }

    create_res = client.post("/api/workspace/queries", json=query_payload, headers=headers)
    assert create_res.status_code == 201
    q_data = create_res.json()
    assert q_data["name"] == "متابعة الشرق الأوسط"
    assert q_data["query_params"]["q"] == "الشرق الأوسط"
    assert q_data["alerts_enabled"] is False  # Explicitly disabled until T19

    query_id = q_data["query_id"]

    # Retrieve specific query
    get_res = client.get(f"/api/workspace/queries/{query_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["query_id"] == query_id

    # List saved queries
    list_res = client.get("/api/workspace/queries", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1
    assert list_res.json()["items"][0]["name"] == "متابعة الشرق الأوسط"

    # Delete query
    del_res = client.delete(f"/api/workspace/queries/{query_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


def test_private_notes_lifecycle(workspace_env):
    """Test creating, reading, updating, and deleting analyst private notes."""
    client = workspace_env["client"]
    token_a = workspace_env["token_a"]
    art1_id = workspace_env["article_1_id"]
    headers = {"Authorization": f"Bearer {token_a}"}

    # 1. Getting non-existent note returns 404
    get_res = client.get(f"/api/workspace/notes/{art1_id}", headers=headers)
    assert get_res.status_code == 404

    # 2. Create note via PUT
    put_res = client.put(
        f"/api/workspace/notes/{art1_id}",
        json={"content": "تحليل أولي: المصدر يركز على الجانب الاقتصادي."},
        headers=headers,
    )
    assert put_res.status_code == 200
    note_data = put_res.json()
    assert note_data["content"] == "تحليل أولي: المصدر يركز على الجانب الاقتصادي."

    # 3. Read note
    read_res = client.get(f"/api/workspace/notes/{art1_id}", headers=headers)
    assert read_res.status_code == 200
    assert read_res.json()["content"] == "تحليل أولي: المصدر يركز على الجانب الاقتصادي."

    # 4. Update note
    update_res = client.put(
        f"/api/workspace/notes/{art1_id}",
        json={"content": "تحليل منقح: تم التحقق من التفاصيل الإضافية."},
        headers=headers,
    )
    assert update_res.status_code == 200
    assert update_res.json()["content"] == "تحليل منقح: تم التحقق من التفاصيل الإضافية."

    # 5. List notes
    list_res = client.get("/api/workspace/notes", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1
    assert list_res.json()["items"][0]["article_id"] == art1_id
    assert list_res.json()["items"][0]["target_available"] is True
    assert list_res.json()["items"][0]["article"]["title"] == "مقال تحليلي أول"

    # 6. Delete note
    del_res = client.delete(f"/api/workspace/notes/{art1_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


def test_strict_cross_user_isolation(workspace_env):
    """
    CRITICAL ACCEPTANCE GATE:
    Verify ID changes cannot expose another owner's resources.
    User B cannot read, list, update, or delete User A's bookmarks, saved queries, or notes.
    """
    client = workspace_env["client"]
    token_a = workspace_env["token_a"]
    token_b = workspace_env["token_b"]
    art1_id = workspace_env["article_1_id"]

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # 1. User A creates resources
    client.post(
        "/api/workspace/bookmarks",
        json={"article_id": art1_id, "notes": "سري للغاية لمحلل أ"},
        headers=headers_a,
    )

    q_res = client.post(
        "/api/workspace/queries",
        json={"name": "استعلام خاص أ", "query_params": {"q": "سر"}},
        headers=headers_a,
    )
    query_id_a = q_res.json()["query_id"]

    client.put(
        f"/api/workspace/notes/{art1_id}",
        json={"content": "ملاحظات محلل أ السرية على المقال"},
        headers=headers_a,
    )

    # 2. User B checks bookmarks: User A's bookmark is NOT visible
    b_bookmarks = client.get("/api/workspace/bookmarks", headers=headers_b)
    assert b_bookmarks.status_code == 200
    assert b_bookmarks.json()["total"] == 0
    assert len(b_bookmarks.json()["items"]) == 0

    # User B checks status of art1_id: is_bookmarked is False for User B
    b_status = client.get(f"/api/workspace/bookmarks/status/{art1_id}", headers=headers_b)
    assert b_status.status_code == 200
    assert b_status.json()["is_bookmarked"] is False

    # User B attempts to delete User A's bookmark: returns 404 (doesn't exist for User B)
    b_del_bm = client.delete(f"/api/workspace/bookmarks/{art1_id}", headers=headers_b)
    assert b_del_bm.status_code == 404

    # 3. User B checks saved queries: User A's query is NOT listed
    b_queries = client.get("/api/workspace/queries", headers=headers_b)
    assert b_queries.status_code == 200
    assert b_queries.json()["total"] == 0

    # User B tries direct ID lookup of User A's query (IDOR attack simulation)
    b_idor_get = client.get(f"/api/workspace/queries/{query_id_a}", headers=headers_b)
    assert b_idor_get.status_code == 404

    # User B tries deleting User A's query by ID
    b_idor_del = client.delete(f"/api/workspace/queries/{query_id_a}", headers=headers_b)
    assert b_idor_del.status_code == 404

    # Confirm User A's query still exists and is untouched
    a_verify_query = client.get(f"/api/workspace/queries/{query_id_a}", headers=headers_a)
    assert a_verify_query.status_code == 200
    assert a_verify_query.json()["name"] == "استعلام خاص أ"

    # 4. User B checks notes on art1_id: returns 404 (does not see User A's note)
    b_get_note = client.get(f"/api/workspace/notes/{art1_id}", headers=headers_b)
    assert b_get_note.status_code == 404

    # User B creates their own note on art1_id
    client.put(
        f"/api/workspace/notes/{art1_id}",
        json={"content": "ملاحظات محلل ب المختلفة تماماً"},
        headers=headers_b,
    )

    # Confirm User A's note remains unaltered
    a_note = client.get(f"/api/workspace/notes/{art1_id}", headers=headers_a)
    assert a_note.status_code == 200
    assert a_note.json()["content"] == "ملاحظات محلل أ السرية على المقال"

    # Confirm User B's note has their own content
    b_note = client.get(f"/api/workspace/notes/{art1_id}", headers=headers_b)
    assert b_note.status_code == 200
    assert b_note.json()["content"] == "ملاحظات محلل ب المختلفة تماماً"
