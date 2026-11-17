"""Comprehensive unit and API tests for Event Comparison across Sources, Timelines, and Divergences."""

from datetime import datetime, timedelta, timezone
from typing import Any

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import (
    get_comparison_service,
    get_current_user,
    get_db,
    get_story_service,
)
from insightbot.api.main import app
from insightbot.models.article import Article, compute_content_hash
from insightbot.models.comparison import (
    DivergenceCategory,
    ReviewStoryRequest,
)
from insightbot.models.story import Story, StoryStatus
from insightbot.models.user import Role, User
from insightbot.modules.stories.comparison import EventComparisonService
from insightbot.modules.stories.service import StoryService


@pytest.fixture
def mock_db() -> Any:
    """In-memory mongomock Database fixture."""
    client: Any = mongomock.MongoClient()
    return client["insightbot_test_comparison"]


@pytest.fixture
def comparison_service(mock_db: Any) -> EventComparisonService:
    return EventComparisonService(mock_db)


@pytest.fixture
def sample_event_story(mock_db: Any) -> tuple[Story, list[Article]]:
    """Seeds a multi-source story with divergent numbers and timeline latency."""
    t0 = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=45)
    t2 = t0 + timedelta(hours=2)

    # Article 1: Al Jazeera (First to report, 12 casualties)
    body1 = "لقي 12 شخصاً مصرعهم وأصيب آخرون في انفجار بمحطة وقود في العاصمة."
    a1 = Article(
        article_id="art-comp-1",
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/event1",
        original_url="https://aljazeera.net/event1",
        resolved_url="https://aljazeera.net/event1",
        title="مصرع 12 شخصاً في انفجار محطة وقود في العاصمة",
        body_text=body1,
        content_hash=compute_content_hash(body1),
        published_at=t0,
        current_version=1,
    )

    # Article 2: Reuters (Reports 45 minutes later with higher death toll: 45 casualties)
    body2 = "ارتفعت حصيلة ضحايا انفجار محطة الوقود إلى 45 قتيلاً وفق ما أعلنته وزارة الصحة."
    a2 = Article(
        article_id="art-comp-2",
        source_id="reuters_ar",
        canonical_url="https://reuters.com/event1",
        original_url="https://reuters.com/event1",
        resolved_url="https://reuters.com/event1",
        title="رويترز: ارتفاع ضحايا انفجار محطة الوقود إلى 45 قتيلاً",
        body_text=body2,
        content_hash=compute_content_hash(body2),
        published_at=t1,
        current_version=1,
    )

    # Article 3: BBC with unknown published date (Defect A13 defense test)
    body3 = "فرق الإنقاذ تواصل البحث عن مفقودين في موقع الانفجار بعد محاصرة النيران للمنطقة."
    a3 = Article(
        article_id="art-comp-3",
        source_id="bbc_ar",
        canonical_url="https://bbc.com/ar/event1",
        original_url="https://bbc.com/ar/event1",
        resolved_url="https://bbc.com/ar/event1",
        title="فرق الإنقاذ تواصل البحث عن مفقودين في موقع الانفجار",
        body_text=body3,
        content_hash=compute_content_hash(body3),
        published_at=None,
        publication_date_unknown_reason="Missing from publisher RSS",
        fetched_at=t2,
        current_version=1,
    )

    # Insert articles into Mongo
    mock_db["articles"].insert_many([
        a1.model_dump(),
        a2.model_dump(),
        a3.model_dump(),
    ])

    story = Story(
        story_id="story-explosion-101",
        title=a1.title,
        status=StoryStatus.PEAK,
        lead_article_id=a1.article_id,
        article_ids=[a1.article_id, a2.article_id, a3.article_id],
        sources=["aljazeera_ar", "reuters_ar", "bbc_ar"],
        article_count=3,
        sources_count=3,
        first_article_at=t0,
        last_article_at=t2,
        created_at=t0,
    )
    mock_db["stories"].insert_one(story.model_dump())

    return story, [a1, a2, a3]


def test_timeline_chronological_and_unknown_dates(
    comparison_service: EventComparisonService, sample_event_story: Any
) -> None:
    """Verify chronological ordering and Defect A13 unknown publication date handling."""
    story, articles = sample_event_story
    report = comparison_service.generate_comparison_report(story.story_id)

    assert report.story_id == story.story_id
    assert report.articles_count == 3
    assert report.sources_count == 3
    assert len(report.timeline) == 3

    # Check order: Al Jazeera (t0), Reuters (t1), BBC (t2 via fetched_at)
    assert report.timeline[0].source_id == "aljazeera_ar"
    assert report.timeline[0].timestamp_basis == "published_at"
    assert report.timeline[0].is_lead_article is True

    assert report.timeline[1].source_id == "reuters_ar"
    assert report.timeline[1].timestamp_basis == "published_at"

    # Defect A13 defense: BBC has no publication date, marked as unknown
    assert report.timeline[2].source_id == "bbc_ar"
    assert report.timeline[2].timestamp_basis == "unknown"


def test_source_perspectives_and_latency(
    comparison_service: EventComparisonService, sample_event_story: Any
) -> None:
    """Verify perspectives grouping, first-reported source, and latency calculation."""
    story, _ = sample_event_story
    report = comparison_service.generate_comparison_report(story.story_id)

    assert report.first_reported_source == "aljazeera_ar"
    assert report.reporting_span_hours == 2.0

    perspectives = {p.source_id: p for p in report.perspectives}
    assert "aljazeera_ar" in perspectives
    assert "reuters_ar" in perspectives
    assert "bbc_ar" in perspectives

    # Al Jazeera was first, latency 0
    assert perspectives["aljazeera_ar"].latency_minutes_from_first == 0
    # Reuters reported 45 minutes later
    assert perspectives["reuters_ar"].latency_minutes_from_first == 45


def test_numerical_and_latency_divergences(
    comparison_service: EventComparisonService, sample_event_story: Any
) -> None:
    """Verify detection of conflicting casualty numbers (12 vs 45) and latency divergence."""
    story, _ = sample_event_story
    report = comparison_service.generate_comparison_report(story.story_id)

    # Must contain numerical divergence (12 vs 45)
    num_diffs = [
        d for d in report.divergent_points if d.category == DivergenceCategory.NUMERICAL_FACTS
    ]
    assert len(num_diffs) >= 1
    diff = num_diffs[0]
    assert "12" in diff.source_a_claim
    assert "45" in diff.source_b_claim
    assert diff.severity == "high"  # 45 / 12 = 3.75 >= 1.5
    assert diff.source_a_citation.startswith("art-comp-1:v1")
    assert diff.source_b_citation.startswith("art-comp-2:v1")

    # Must contain timeline latency divergence (> 30 min lag)
    time_diffs = [
        d for d in report.divergent_points if d.category == DivergenceCategory.TIMELINE_LATENCY
    ]
    assert len(time_diffs) >= 1
    assert "45 دقيقة" in time_diffs[0].description


def test_versioned_evidence_citations(
    comparison_service: EventComparisonService, sample_event_story: Any
) -> None:
    """Verify versioned evidence items point to immutable version without unbounded full body."""
    story, _ = sample_event_story
    report = comparison_service.generate_comparison_report(story.story_id)

    assert len(report.evidence_items) == 3
    for ev in report.evidence_items:
        assert ev.article_id in ["art-comp-1", "art-comp-2", "art-comp-3"]
        assert ev.version == 1
        assert len(ev.exact_quote) <= 180
        assert ev.canonical_url.startswith("https://")


def test_analyst_review_and_article_exclusion(
    comparison_service: EventComparisonService, mock_db: Any, sample_event_story: Any
) -> None:
    """Verify analyst can submit review and exclude mismatched article with audit trail."""
    story, _ = sample_event_story

    req = ReviewStoryRequest(
        status="verified",
        notes="تم التحقق من تباين حصيلة الضحايا بين المصادر واستبعاد تقرير غير دقيق",
        excluded_article_ids=["art-comp-3"],
    )

    review = comparison_service.submit_analyst_review(
        story_id=story.story_id, reviewer_id="analyst-user-42", request=req
    )

    assert review.status == "verified"
    assert review.reviewer_id == "analyst-user-42"
    assert review.excluded_article_ids == ["art-comp-3"]

    # Verify story was updated and version incremented
    updated_story = mock_db["stories"].find_one({"story_id": story.story_id})
    assert updated_story["version"] == 2
    assert "art-comp-3" not in updated_story["article_ids"]
    assert updated_story["article_count"] == 2

    # Verify immutable snapshot was captured
    snapshots = list(mock_db["story_snapshots"].find({"story_id": story.story_id}))
    assert len(snapshots) == 1
    assert snapshots[0]["version"] == 1

    # Verify audit entry was logged
    audits = list(mock_db["story_audits"].find({"story_id": story.story_id}))
    assert len(audits) >= 1
    assert audits[-1]["actor_id"] == "analyst-user-42"


def test_comparison_api_endpoints(mock_db: Any, sample_event_story: Any) -> None:
    """Verify GET /api/stories/{id}/comparison and POST /api/stories/{id}/review endpoints."""
    story, _ = sample_event_story
    client = TestClient(app)

    # 1. Anonymous / Unauthenticated gets 401
    res_anon = client.get(f"/api/stories/{story.story_id}/comparison")
    assert res_anon.status_code == 401

    # Override dependencies for testing
    viewer_user = User(user_id="viewer-1", username="viewer", role=Role.VIEWER, password_hash="dummy_hash")
    analyst_user = User(user_id="analyst-1", username="analyst", role=Role.ANALYST, password_hash="dummy_hash")

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_comparison_service] = lambda: EventComparisonService(mock_db)
    app.dependency_overrides[get_story_service] = lambda: StoryService(mock_db)

    # 2. Viewer can view comparison report
    app.dependency_overrides[get_current_user] = lambda: viewer_user
    res = client.get(f"/api/stories/{story.story_id}/comparison")
    assert res.status_code == 200
    data = res.json()
    assert data["story_id"] == story.story_id
    assert len(data["timeline"]) == 3
    assert len(data["perspectives"]) == 3
    assert len(data["divergent_points"]) >= 1

    # 3. Viewer is FORBIDDEN (403) from submitting Analyst review
    rev_payload = {
        "status": "flagged",
        "notes": "التقرير يحتوي على تباينات تتطلب مراجعة إضافية",
        "excluded_article_ids": [],
    }
    res_rev_viewer = client.post(f"/api/stories/{story.story_id}/review", json=rev_payload)
    assert res_rev_viewer.status_code == 403

    # 4. Analyst CAN submit review (200)
    app.dependency_overrides[get_current_user] = lambda: analyst_user
    res_rev_analyst = client.post(f"/api/stories/{story.story_id}/review", json=rev_payload)
    assert res_rev_analyst.status_code == 200
    rev_data = res_rev_analyst.json()
    assert rev_data["status"] == "flagged"
    assert rev_data["reviewer_id"] == "analyst-1"

    app.dependency_overrides.clear()
