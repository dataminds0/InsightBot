"""Comprehensive unit and API tests for in-app alerts, replay dedup, and analyst assistant."""

from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import (
    get_alert_service,
    get_assistant_repository,
    get_assistant_service,
    get_current_user,
    get_db,
    get_notification_repository,
)
from insightbot.api.main import app
from insightbot.models.assistant import AssistantAskRequest
from insightbot.models.notifications import AlertToggleRequest, InAppNotification
from insightbot.models.user import Role, User
from insightbot.modules.alerts.service import AlertService
from insightbot.modules.assistant.service import AssistantService
from insightbot.modules.generation.engine import LocalEvidenceGenerationEngine
from insightbot.modules.generation.service import GenerationService
from insightbot.repositories.assistant_repository import (
    AssistantJobRepository,
)
from insightbot.repositories.notification_repository import NotificationRepository


@pytest.fixture
def mock_db():
    client = mongomock.MongoClient()
    return client["test_insightbot"]


@pytest.fixture
def analyst_user():
    return User(
        user_id="analyst-1",
        username="analyst1",
        email="analyst@insightbot.local",
        name="Analyst One",
        role=Role.ANALYST,
        is_active=True,
        password_hash="dummy_hash",
    )


@pytest.fixture
def viewer_user():
    return User(
        user_id="viewer-1",
        username="viewer1",
        email="viewer@insightbot.local",
        name="Viewer One",
        role=Role.VIEWER,
        is_active=True,
        password_hash="dummy_hash",
    )


@pytest.fixture
def other_user():
    return User(
        user_id="other-user",
        username="otheruser",
        email="other@insightbot.local",
        name="Other User",
        role=Role.ANALYST,
        is_active=True,
        password_hash="dummy_hash",
    )


@pytest.fixture
def notification_repo(mock_db):
    return NotificationRepository(mock_db)


@pytest.fixture
def alert_service(mock_db, notification_repo):
    return AlertService(mock_db, notification_repo)


@pytest.fixture
def assistant_repo(mock_db):
    return AssistantJobRepository(mock_db)


@pytest.fixture
def assistant_service(mock_db, assistant_repo):
    engine = LocalEvidenceGenerationEngine()
    gen_service = GenerationService(mock_db, engine=engine)
    return AssistantService(mock_db, assistant_repo, gen_service, engine)


@pytest.fixture
def client(mock_db, notification_repo, alert_service, assistant_repo, assistant_service, analyst_user):
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_notification_repository] = lambda: notification_repo
    app.dependency_overrides[get_alert_service] = lambda: alert_service
    app.dependency_overrides[get_assistant_repository] = lambda: assistant_repo
    app.dependency_overrides[get_assistant_service] = lambda: assistant_service
    app.dependency_overrides[get_current_user] = lambda: analyst_user

    yield TestClient(app)
    app.dependency_overrides.clear()


def test_saved_query_alert_and_replay_idempotency(alert_service, notification_repo, mock_db):
    """Test that saved queries trigger alerts, and replay on identical articles NEVER duplicates notifications."""
    user_id = "user-123"
    query_id = "q-oil-price"

    # Setup active saved query
    mock_db["saved_queries"].insert_one(
        {
            "user_id": user_id,
            "query_id": query_id,
            "name": "تنبيه النفط والطاقة",
            "query_params": {"q": "النفط"},
            "alerts_enabled": True,
            "is_paused": False,
            "cooldown_hours": 1,
            "last_alert_at": None,
        }
    )

    article = {
        "article_id": "art-100",
        "title": "ارتفاع أسعار النفط العالمية اليوم",
        "body_text": "شهدت أسواق النفط ارتفاعاً ملحوظاً اليوم في التعاملات الصباحية.",
        "source_id": "aljazeera",
        "language": "ar",
        "version": 1,
    }

    # Run 1: First evaluation should generate notification
    notifs_run1 = alert_service.evaluate_article_alerts(article)
    assert len(notifs_run1) == 1
    assert notifs_run1[0].user_id == user_id
    assert notifs_run1[0].target_id == "art-100"
    assert "النفط والطاقة" in notifs_run1[0].title
    assert notification_repo.count_unread(user_id) == 1

    # Run 2 (Replay test): Replaying the exact same article MUST NOT create duplicate notification
    notifs_run2 = alert_service.evaluate_article_alerts(article)
    assert len(notifs_run2) == 0, "Replay must be idempotent and produce 0 duplicate notifications"
    assert notification_repo.count_unread(user_id) == 1, "Unread count must stay strictly at 1"

    # Run 3 (Replay test again): Replay again
    notifs_run3 = alert_service.evaluate_article_alerts(article)
    assert len(notifs_run3) == 0
    assert notification_repo.count_unread(user_id) == 1


def test_alert_cooldown_and_pause_defense(alert_service, mock_db):
    """Test that cooldown window and pause state cleanly suppress excessive notifications."""
    user_id = "user-abc"
    query_id = "q-tech"

    # Setup saved query with 2-hour cooldown
    mock_db["saved_queries"].insert_one(
        {
            "user_id": user_id,
            "query_id": query_id,
            "name": "تنبيه التقنية",
            "query_params": {"q": "ذكاء"},
            "alerts_enabled": True,
            "is_paused": False,
            "cooldown_hours": 2,
            "last_alert_at": None,
        }
    )

    art1 = {
        "article_id": "art-tech-1",
        "title": "تطورات جديدة في نماذج الذكاء الاصطناعي",
        "body_text": "تقرير حول تقنيات الذكاء وتطبيقاتها.",
        "source_id": "tech_source",
        "language": "ar",
    }

    art2 = {
        "article_id": "art-tech-2",
        "title": "الذكاء الاصطناعي في الطب",
        "body_text": "استخدامات حديثة للذكاء الاصطناعي في الرعاية الصحية.",
        "source_id": "tech_source",
        "language": "ar",
    }

    # First article triggers alert
    res1 = alert_service.evaluate_article_alerts(art1)
    assert len(res1) == 1

    # Second article arrives 10 minutes later (well within 2-hour cooldown)
    res2 = alert_service.evaluate_article_alerts(art2)
    assert len(res2) == 0, "Second article within cooldown window must be suppressed"

    # Pause query
    alert_service.configure_saved_query_alert(
        user_id,
        AlertToggleRequest(query_id=query_id, alerts_enabled=True, is_paused=True, cooldown_hours=2),
    )

    art3 = {
        "article_id": "art-tech-3",
        "title": "مؤتمر الذكاء الاصطناعي الدولي",
        "body_text": "افتتاح المؤتمر اليوم.",
        "source_id": "tech_source",
        "language": "ar",
    }
    # Expire cooldown artificially
    mock_db["saved_queries"].update_one(
        {"query_id": query_id},
        {"$set": {"last_alert_at": datetime.now(timezone.utc) - timedelta(hours=3)}},
    )
    res3 = alert_service.evaluate_article_alerts(art3)
    assert len(res3) == 0, "Paused query must never produce alerts"


def test_notification_read_and_api_lifecycle(client, notification_repo, analyst_user):
    """Test listing, read count, marking read, and deleting notifications via API."""
    user_id = analyst_user.user_id

    # Create 3 test notifications
    n1 = notification_repo.create_notification(
        InAppNotification(
            user_id=user_id,
            title="تنبيه 1",
            message="رسالة 1",
            notification_type="saved_query_match",
            target_type="article",
            target_id="art-1",
        )
    )
    n2 = notification_repo.create_notification(
        InAppNotification(
            user_id=user_id,
            title="تنبيه 2",
            message="رسالة 2",
            notification_type="story_update",
            target_type="story",
            target_id="story-1",
        )
    )

    # Check unread count
    r = client.get("/api/notifications/unread-count")
    assert r.status_code == 200
    assert r.json()["unread_count"] == 2

    # List notifications
    r = client.get("/api/notifications")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Mark single read
    r = client.patch(f"/api/notifications/{n1.notification_id}/read")
    assert r.status_code == 200
    assert notification_repo.count_unread(user_id) == 1

    # Mark all read
    r = client.post("/api/notifications/read-all")
    assert r.status_code == 200
    assert notification_repo.count_unread(user_id) == 0

    # Delete notification
    r = client.delete(f"/api/notifications/{n2.notification_id}")
    assert r.status_code == 200
    assert notification_repo.count_total(user_id) == 1


def test_assistant_citation_unavailability_validation(mock_db, assistant_service, analyst_user):
    """Test that deleted/unavailable target articles are explicitly flagged in citations, not silently latest."""
    now = datetime.now(timezone.utc)
    # Insert an article that will be deleted
    mock_db["articles"].insert_one(
        {
            "article_id": "art-cit-1",
            "title": "بيان رسمي حول الأزمة الدبلوماسية",
            "body_text": "صرح المتحدث الرسمي بأن الجهود مستمرة لحل الأزمة الدبلوماسية وسنواصل الحوار.",
            "source_id": "source_official",
            "canonical_url": "https://official.gov/news/1",
            "current_version": 1,
            "version": 1,
            "language": "ar",
            "quarantined": False,
            "fetched_at": now.isoformat(),
            "published_at": now.isoformat(),
        }
    )

    mock_db["stories"].insert_one(
        {
            "story_id": "story-dip",
            "title": "الأزمة الدبلوماسية",
            "version": 1,
            "article_ids": ["art-cit-1"],
            "created_at": now,
            "updated_at": now,
        }
    )

    req = AssistantAskRequest(
        query="ما هو تصريح المتحدث الرسمي حول الأزمة؟",
        story_id="story-dip",
        max_passages=6,
    )

    # 1. Ask while article exists
    ans1 = assistant_service.ask_sync(analyst_user.user_id, req)
    assert not ans1.abstained
    assert len(ans1.citations) > 0
    assert ans1.citations[0].is_valid is True

    # 2. Delete article (target becomes unavailable in repository)
    mock_db["articles"].delete_one({"article_id": "art-cit-1"})

    # 3. Citation validation should catch unavailability and mark is_valid=False
    validated = assistant_service._validate_citations_availability(ans1)
    for cit in validated.citations:
        if cit.article_id == "art-cit-1":
            assert cit.is_valid is False
            assert "غير متاح حالياً" in cit.quote


def test_assistant_job_queue_and_cancellation(client, assistant_repo, analyst_user, other_user):
    """Test queue bounding, asynchronous job polling, and cancellation with IDOR defense."""
    # Submit job 1
    r1 = client.post(
        "/api/assistant/ask?async_mode=true",
        json={"query": "السؤال الأول للتحليل", "max_passages": 4},
    )
    assert r1.status_code == 200
    job1_data = r1.json()["job"]
    job1_id = job1_data["job_id"]
    assert job1_data["status"] == "pending"

    # Submit job 2
    r2 = client.post(
        "/api/assistant/ask?async_mode=true",
        json={"query": "السؤال الثاني للتحليل", "max_passages": 4},
    )
    assert r2.status_code == 200

    # Submit job 3 (Queue full defense: MAX_QUEUED_JOBS = 2)
    r3 = client.post(
        "/api/assistant/ask?async_mode=true",
        json={"query": "السؤال الثالث للتحليل", "max_passages": 4},
    )
    assert r3.status_code == 429
    assert "limit exceeded" in r3.json()["detail"].lower()

    # Cancel job 1
    r_cancel = client.post(f"/api/assistant/jobs/{job1_id}/cancel")
    assert r_cancel.status_code == 200
    assert r_cancel.json()["status"] == "cancelled"

    # Verify status changed to cancelled
    r_poll = client.get(f"/api/assistant/jobs/{job1_id}")
    assert r_poll.status_code == 200
    assert r_poll.json()["status"] == "cancelled"

    # IDOR Defense: Switch current user to other_user and attempt to access job1
    app.dependency_overrides[get_current_user] = lambda: other_user
    r_idor = client.get(f"/api/assistant/jobs/{job1_id}")
    assert r_idor.status_code == 403, "Access to another user's assistant job must be forbidden"
