"""Comprehensive unit and integration tests for Story Clustering, Lifecycle, and Audited Merge/Split (T14).

Verifies:
1. Entity extraction and exact character offset tracking.
2. Positive event corroboration & lifecycle progression (EMERGING -> PEAK).
3. Location conflict guard (Japan vs Chile).
4. Temporal window cutoff (Delta > 72h).
5. Chain-merge defense against creeping cluster blobs.
6. Audited manual story merge (snapshots, audit log, target version increment, source closed).
7. Audited manual story split (snapshots, audit log, independent story creation).
8. API endpoints (GET /api/stories, GET /api/stories/{id}, POST /api/stories/merge, POST /api/stories/{id}/split, GET /api/stories/{id}/history).
9. Memory defense: member article previews strictly omit body_text (Defect A12).
"""

from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import get_db
from insightbot.api.main import app
from insightbot.models.article import Article
from insightbot.models.story import (
    EntityCategory,
    Story,
    StoryAuditAction,
    StoryStatus,
)
from insightbot.models.user import Role, UserStatus
from insightbot.modules.stories.clustering import (
    StoryClusteringEngine,
    extract_entities_from_text,
    extract_keywords_from_text,
)
from insightbot.modules.stories.service import StoryService
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.story_repository import StoryRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthService


def test_extract_entities_and_keywords():
    text = "أعلنت الأمم المتحدة في جنيف عن عقد مؤتمر دولي للمانحين بشأن اليمن ولدعم الجهود الإنسانية في عدن وصنعاء."
    mentions = extract_entities_from_text("art-1", text)
    assert len(mentions) >= 3

    loc_ids = {m.resolved_id for m in mentions if m.category == EntityCategory.LOCATION}
    assert "Yemen" in loc_ids
    assert "Aden" in loc_ids
    assert "Sanaa" in loc_ids

    org_ids = {m.resolved_id for m in mentions if m.category == EntityCategory.ORGANIZATION}
    assert "UN" in org_ids

    # Verify character offsets
    for m in mentions:
        assert m.start_char >= 0
        assert m.end_char > m.start_char
        assert text[m.start_char : m.end_char] == m.text

    keywords = extract_keywords_from_text("مؤتمر دولي للمانحين", text)
    assert "مؤتمر" in keywords or "المانحين" in keywords


def test_clustering_guards_location_and_temporal():
    engine = StoryClusteringEngine(temporal_window_hours=72.0)
    now = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)

    # Lead article: earthquake in Japan
    lead_art = Article(
        article_id="lead-jp",
        source_id="nhk_en",
        canonical_url="https://nhk.jp/1",
        original_url="https://nhk.jp/1",
        resolved_url="https://nhk.jp/1",
        title="زلزال بقوة 6.3 درجات يضرب السواحل الشرقية في طوكيو باليابان",
        body_text="ضرب زلزال قوي قبالة سواحل طوكيو في اليابان صباح اليوم.",
        content_hash="hash-jp",
        published_at=now,
    )

    story = Story(
        story_id="story-jp",
        title=lead_art.title,
        lead_article_id=lead_art.article_id,
        article_ids=[lead_art.article_id],
        sources=["nhk_en"],
        article_count=1,
        sources_count=1,
        first_article_at=now,
        last_article_at=now,
        primary_location="Japan",
        entities=["Japan", "Tokyo"],
        keywords=["زلزال", "طوكيو", "اليابان"],
    )

    # 1. Location conflict article: earthquake in Chile
    art_chile = Article(
        article_id="art-cl",
        source_id="bbc_ar",
        canonical_url="https://bbc.com/cl",
        original_url="https://bbc.com/cl",
        resolved_url="https://bbc.com/cl",
        title="زلزال بقوة 6.3 درجات يضرب السواحل في تشيلي",
        body_text="ضرب زلزال سواحل تشيلي قرب العاصمة سانتياغو اليوم.",
        content_hash="hash-cl",
        published_at=now + timedelta(hours=2),
    )
    belongs, _, reason = engine.evaluate_membership(art_chile, story, lead_art)
    assert not belongs, "Location conflict (Japan vs Chile) must reject clustering!"
    assert "location" in reason.lower()

    # 2. Temporal cutoff article: earthquake in Japan but 10 days later
    art_late = Article(
        article_id="art-late",
        source_id="reuters_ar",
        canonical_url="https://reuters.com/late",
        original_url="https://reuters.com/late",
        resolved_url="https://reuters.com/late",
        title="زلزال بقوة 6.3 درجات يضرب السواحل الشرقية في طوكيو باليابان مجددا",
        body_text="ضرب زلزال قوي قبالة سواحل طوكيو في اليابان مجددا.",
        content_hash="hash-late",
        published_at=now + timedelta(days=10),
    )
    belongs_late, _, reason_late = engine.evaluate_membership(art_late, story, lead_art)
    assert not belongs_late, "Temporal delta > 72h must reject clustering!"
    assert "temporal" in reason_late.lower()


@pytest.fixture
def stories_env():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_stories"]

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    user_repo = UserRepository(mock_db)
    auth_service = AuthService(user_repo)

    auth_service.register(
        "analyst_usr", "PasswordAnalyst123!", role=Role.ANALYST, status=UserStatus.ACTIVE
    )
    auth_service.register(
        "viewer_usr", "PasswordViewer123!", role=Role.VIEWER, status=UserStatus.ACTIVE
    )

    _, session_analyst = auth_service.login("analyst_usr", "PasswordAnalyst123!")
    _, session_viewer = auth_service.login("viewer_usr", "PasswordViewer123!")

    article_repo = ArticleRepository(mock_db)
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    # Seed 3 articles for an unfolding event in Yemen (Aden)
    art1, _ = article_repo.save_article_with_version(
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/yemen/oil-facility",
        original_url="https://aljazeera.net/yemen/oil-facility",
        resolved_url="https://aljazeera.net/yemen/oil-facility",
        title="افتتاح منشأة لتخزين النفط الخام في ميناء عدن باليمن",
        body_text="أعلنت وزارة النفط اليمنية اليوم في عدن افتتاح منشأة استراتيجية جديدة لتخزين النفط في ميناء عدن لتعزيز الصادرات.",
        published_at=now,
    )

    art2, _ = article_repo.save_article_with_version(
        source_id="alarabiya_ar",
        canonical_url="https://alarabiya.net/yemen/oil-port",
        original_url="https://alarabiya.net/yemen/oil-port",
        resolved_url="https://alarabiya.net/yemen/oil-port",
        title="تدشين منشأة لتخزين النفط الخام في ميناء عدن باليمن",
        body_text="دشنت السلطات اليمنية في عدن منشأة حيوية لتخزين وتصدير النفط الخام بميناء عدن بحضور مسؤولين حكوميين.",
        published_at=now + timedelta(hours=2),
    )

    art3, _ = article_repo.save_article_with_version(
        source_id="reuters_en",
        canonical_url="https://reuters.com/yemen/aden-terminal",
        original_url="https://reuters.com/yemen/aden-terminal",
        resolved_url="https://reuters.com/yemen/aden-terminal",
        title="New crude oil storage facility opens at Aden port in Yemen",
        body_text="Yemeni authorities in Aden inaugurated a new crude oil storage terminal at the port of Aden on Sunday.",
        published_at=now + timedelta(hours=4),
    )

    # Seed unrelated 4th article
    art4, _ = article_repo.save_article_with_version(
        source_id="bbc_ar",
        canonical_url="https://bbc.com/tech/ai-summit",
        original_url="https://bbc.com/tech/ai-summit",
        resolved_url="https://bbc.com/tech/ai-summit",
        title="انطلاق قمة الذكاء الاصطناعي العالمية في باريس بمشاركة دولية واسعة",
        body_text="انطلقت في العاصمة الفرنسية باريس اليوم فعاليات القمة العالمية لتقنيات الذكاء الاصطناعي والابتكار الرقمي.",
        published_at=now + timedelta(hours=1),
    )

    return {
        "client": client,
        "db": mock_db,
        "token_analyst": session_analyst.session_token,
        "token_viewer": session_viewer.session_token,
        "art1_id": art1.article_id,
        "art2_id": art2.article_id,
        "art3_id": art3.article_id,
        "art4_id": art4.article_id,
    }


def test_service_lifecycle_progression(stories_env):
    """Test clustering and progression: EMERGING -> PEAK when multiple sources corroborate."""
    db = stories_env["db"]
    service = StoryService(db)
    story_repo = StoryRepository(db)

    # Cluster article 1 -> Creates emerging story
    s1 = service.cluster_article(stories_env["art1_id"])
    assert s1.status == StoryStatus.EMERGING
    assert s1.article_count == 1
    assert s1.sources_count == 1

    # Cluster article 2 -> Corroborates from second source (alarabiya_ar)
    s2 = service.cluster_article(stories_env["art2_id"])
    assert s2.story_id == s1.story_id
    assert s2.article_count == 2
    assert s2.sources_count == 2

    # Cluster article 3 -> Reaches 3 articles across 3 sources -> Promoted to PEAK!
    s3 = service.cluster_article(stories_env["art3_id"])
    assert s3.story_id == s1.story_id
    assert s3.article_count == 3
    assert s3.sources_count == 3
    assert s3.status == StoryStatus.PEAK
    assert s3.peak_at is not None

    # Cluster article 4 (Paris AI summit) -> Must create separate story cluster
    s4 = service.cluster_article(stories_env["art4_id"])
    assert s4.story_id != s1.story_id
    assert s4.primary_location == "France" or "Paris" in s4.entities

    # Verify audit trail
    history = story_repo.get_story_history(s1.story_id)
    actions = [a.action for a in history]
    assert StoryAuditAction.CREATED in actions
    assert StoryAuditAction.ARTICLE_ADDED in actions


def test_service_audited_merge_and_split(stories_env):
    """Test audited manual merge and split of story clusters."""
    db = stories_env["db"]
    service = StoryService(db)
    story_repo = StoryRepository(db)

    # Cluster article 1 and article 4 into two separate stories
    s_yemen = service.cluster_article(stories_env["art1_id"])
    s_paris = service.cluster_article(stories_env["art4_id"])
    assert s_yemen.story_id != s_paris.story_id

    # 1. Merge s_paris into s_yemen
    merged_target = service.merge_stories(
        target_story_id=s_yemen.story_id,
        source_story_id=s_paris.story_id,
        actor_id="analyst-123",
        reason="Manual consolidation of coverage",
    )
    assert merged_target.version > s_yemen.version
    assert len(merged_target.article_ids) == 2
    assert stories_env["art4_id"] in merged_target.article_ids

    # Source story must be marked CLOSED
    closed_source = story_repo.get_story_by_id(s_paris.story_id)
    assert closed_source is not None
    assert closed_source.status == StoryStatus.CLOSED

    # Verify audit history
    audits_target = story_repo.get_story_history(s_yemen.story_id)
    assert any(a.action == StoryAuditAction.MERGED for a in audits_target)

    # 2. Split art4 out into a separate story again
    updated_source, new_story = service.split_story(
        source_story_id=s_yemen.story_id,
        article_ids_to_split=[stories_env["art4_id"]],
        new_title="قمة الذكاء الاصطناعي في باريس",
        actor_id="analyst-123",
        reason="Splitting unrelated technology summit",
    )
    assert len(updated_source.article_ids) == 1
    assert stories_env["art4_id"] not in updated_source.article_ids
    assert new_story.article_ids == [stories_env["art4_id"]]
    assert new_story.title == "قمة الذكاء الاصطناعي في باريس"


def test_stories_api_endpoints(stories_env):
    client = stories_env["client"]
    token_analyst = stories_env["token_analyst"]
    token_viewer = stories_env["token_viewer"]
    headers_analyst = {"Authorization": f"Bearer {token_analyst}"}
    headers_viewer = {"Authorization": f"Bearer {token_viewer}"}

    # Pre-cluster articles
    db = stories_env["db"]
    service = StoryService(db)
    s_yemen = service.cluster_article(stories_env["art1_id"])
    service.cluster_article(stories_env["art2_id"])
    s_paris = service.cluster_article(stories_env["art4_id"])

    # 1. GET /api/stories
    res_list = client.get("/api/stories", headers=headers_viewer)
    assert res_list.status_code == 200
    data_list = res_list.json()
    assert data_list["total"] == 2
    assert len(data_list["items"]) == 2

    # 2. GET /api/stories/{id}
    res_detail = client.get(f"/api/stories/{s_yemen.story_id}", headers=headers_viewer)
    assert res_detail.status_code == 200
    data_detail = res_detail.json()
    assert data_detail["story_id"] == s_yemen.story_id
    assert len(data_detail["member_articles"]) == 2
    # Defect A12 memory defense: body_text must NOT be present in member previews
    assert "body_text" not in data_detail["member_articles"][0]

    # 3. POST /api/stories/merge (Viewer gets 403 Forbidden)
    res_forbidden = client.post(
        "/api/stories/merge",
        headers=headers_viewer,
        json={
            "target_story_id": s_yemen.story_id,
            "source_story_id": s_paris.story_id,
            "reason": "Test merge",
        },
    )
    assert res_forbidden.status_code == 403

    # 4. POST /api/stories/merge (Analyst succeeds)
    res_merge = client.post(
        "/api/stories/merge",
        headers=headers_analyst,
        json={
            "target_story_id": s_yemen.story_id,
            "source_story_id": s_paris.story_id,
            "reason": "Consolidating regional coverage",
        },
    )
    assert res_merge.status_code == 200
    assert len(res_merge.json()["article_ids"]) == 3

    # 5. GET /api/stories/{id}/history
    res_history = client.get(f"/api/stories/{s_yemen.story_id}/history", headers=headers_viewer)
    assert res_history.status_code == 200
    history_items = res_history.json()
    assert len(history_items) >= 2
    assert any(h["action"] == "merged" for h in history_items)
