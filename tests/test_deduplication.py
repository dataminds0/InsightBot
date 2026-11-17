"""Comprehensive unit and integration tests for Deduplication & Syndication Tracking (T13).

Verifies:
1. Exact content hash deduplication (EXACT_HASH or SYNDICATION).
2. Wire syndication recognition (shared wire service attribution).
3. Near-duplicate shingling (Jaccard >= 0.85).
4. DEFECT DEFENSE: Similar headlines with divergent numerical values are strictly rejected.
5. Temporal candidate window (72h cutoff for near-duplicates).
6. Idempotency and replay stability.
7. API endpoints (GET /api/articles/{id}/duplicates, POST /api/articles/{id}/deduplicate).
8. RBAC and non-leakage of full body_text in previews (Defect A12).
"""

import hashlib
from datetime import datetime, timedelta, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import get_db
from insightbot.api.main import app
from insightbot.models.article import Article
from insightbot.models.duplicate import DuplicateType
from insightbot.models.user import Role, UserStatus
from insightbot.modules.deduplication.detector import (
    DeduplicationEngine,
    compute_headline_similarity,
    compute_shingle_jaccard,
    detect_wire_agency,
    extract_numbers,
    normalize_text_for_dedup,
)
from insightbot.modules.deduplication.service import DeduplicationService
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.duplicate_repository import DuplicateRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthService


def make_test_article(
    article_id: str,
    source_id: str,
    title: str,
    body_text: str,
    published_at: datetime,
) -> Article:
    """Helper to instantiate valid domain Article."""
    chash = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    url = f"https://example.com/news/{article_id}"
    return Article(
        article_id=article_id,
        source_id=source_id,
        canonical_url=url,
        original_url=url,
        resolved_url=url,
        title=title,
        body_text=body_text,
        content_hash=chash,
        published_at=published_at,
    )


def test_normalize_text_and_numbers():
    arabic_raw = "عاجل: مقتل ١٥ شخصاً في حادث سير مروع!"
    normalized = normalize_text_for_dedup(arabic_raw)
    assert "15" in normalized
    assert "شخصا" in normalized or "شخص" in normalized

    nums = extract_numbers("أكدت المصادر مقتل 12 جنديا وإصابة 45 آخرين")
    assert "12" in nums
    assert "45" in nums

    nums_eastern = extract_numbers("بلغت الحصيلة ٧٠ قتيلاً")
    assert "70" in nums_eastern


def test_detect_wire_agency():
    assert detect_wire_agency("(رويترز) - أعلنت وزارة الطاقة اليوم...") == "Reuters"
    assert detect_wire_agency("باريس (أ ف ب) — أصدرت الرئاسة بياناً...") == "AFP"
    assert detect_wire_agency("MOSCOW (TASS) - Foreign ministry confirmed...") == "TASS"
    assert detect_wire_agency("WASHINGTON (AP) — The Senate voted...") == "AP"
    assert detect_wire_agency("تقرير خاص وحصري من مراسلنا في الميدان") is None


def test_compute_shingle_jaccard_and_headline():
    text1 = "أعلنت وزارة الصحة عن تسجيل إصابات جديدة بالفيروس خلال الساعات الماضية في جميع المحافظات"
    text2 = "أعلنت وزارة الصحة عن تسجيل إصابات جديدة بالفيروس خلال الساعات الماضية في كل المحافظات"
    sim = compute_shingle_jaccard(text1, text2, k=3)
    assert sim >= 0.65

    h1 = "ارتفاع أسعار النفط عالميا اليوم مع تصاعد التوترات"
    h2 = "ارتفاع أسعار النفط عالميا اليوم إثر تصاعد التوترات"
    h_sim = compute_headline_similarity(h1, h2)
    assert h_sim >= 0.70


def test_defect_defense_divergent_numbers_in_headlines():
    """
    CRITICAL DEFECT DEFENSE:
    Two articles with very similar headlines but different numbers (e.g. 12 vs 45)
    must NOT be collapsed as duplicates.
    """
    engine = DeduplicationEngine(near_duplicate_threshold=0.85)

    art_a = make_test_article(
        article_id="art-12",
        source_id="src_1",
        title="مقتل 12 شخصا في انفجار شاحنة وقود شمالي البلاد",
        body_text="لقي 12 شخصا حتفهم اليوم إثر انفجار شاحنة وقود على الطريق السريع وفق ما أفادت به الشرطة المحلية في بيان رسمي.",
        published_at=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
    )

    art_b = make_test_article(
        article_id="art-45",
        source_id="src_2",
        title="مقتل 45 شخصا في انفجار شاحنة وقود شمالي البلاد",
        body_text="لقي 45 شخصا حتفهم اليوم إثر انفجار شاحنة وقود على الطريق السريع وفق ما أفادت به مصادر طبية في تحديث جديد للحصيلة.",
        published_at=datetime(2026, 11, 15, 10, 30, tzinfo=timezone.utc),
    )

    # Comparing them must return None because of the divergent numbers defense
    rel = engine.compare(art_a, art_b)
    assert rel is None, "Divergent numbers in headlines (12 vs 45) must strictly reject deduplication!"


def test_exact_hash_and_syndication_comparison():
    engine = DeduplicationEngine()

    # Two articles from different sources republishing the exact same Reuters wire article
    art_a = make_test_article(
        article_id="art-canonical",
        source_id="aljazeera_ar",
        title="رويترز: اتفاق مبدئي لخفض الإنتاج بين كبار المنتجين",
        body_text="(رويترز) - توصل المنتجون الرئيسيون إلى اتفاق مبدئي لخفض معدلات الإنتاج بمقدار مليوني برميل يوميا.",
        published_at=datetime(2026, 11, 15, 8, 0, tzinfo=timezone.utc),
    )

    art_b = make_test_article(
        article_id="art-duplicate",
        source_id="alarabiya_ar",
        title="اتفاق مبدئي لخفض الإنتاج بين المنتجين وفق رويترز",
        body_text="(رويترز) - توصل المنتجون الرئيسيون إلى اتفاق مبدئي لخفض معدلات الإنتاج بمقدار مليوني برميل يوميا.",
        published_at=datetime(2026, 11, 15, 8, 45, tzinfo=timezone.utc),
    )

    rel = engine.compare(art_a, art_b)
    assert rel is not None
    assert rel.canonical_article_id == "art-canonical"
    assert rel.duplicate_article_id == "art-duplicate"
    assert rel.duplicate_type == DuplicateType.SYNDICATION
    assert rel.evidence.shared_wire_agency == "Reuters"
    assert rel.similarity_score == 1.0


def test_temporal_cutoff_for_near_duplicates():
    engine = DeduplicationEngine(near_duplicate_threshold=0.85, temporal_window_hours=72.0)

    # Similar text but published 10 days apart (beyond 72h window)
    art_a = make_test_article(
        article_id="art-early",
        source_id="src_1",
        title="افتتاح المؤتمر الاقتصادي السنوي في العاصمة",
        body_text="افتتح رئيس الوزراء اليوم فعاليات المؤتمر الاقتصادي السنوي لمناقشة آفاق الاستثمار وجذب رؤوس الأموال الأجنبية.",
        published_at=datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc),
    )

    art_b = make_test_article(
        article_id="art-late",
        source_id="src_2",
        title="افتتاح فعاليات المؤتمر الاقتصادي السنوي في العاصمة",
        body_text="افتتح رئيس الوزراء فعاليات المؤتمر الاقتصادي السنوي لمناقشة آفاق الاستثمار وجذب رؤوس الأموال الأجنبية اليوم.",
        published_at=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
    )

    # Outside the 72h window, near-duplicate comparison returns None
    rel = engine.compare(art_a, art_b)
    assert rel is None


@pytest.fixture
def dedup_env():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_dedup"]

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    user_repo = UserRepository(mock_db)
    auth_service = AuthService(user_repo)

    # Users
    auth_service.register(
        "analyst_user", "PasswordAnalyst123!", role=Role.ANALYST, status=UserStatus.ACTIVE
    )
    auth_service.register(
        "viewer_user", "PasswordViewer123!", role=Role.VIEWER, status=UserStatus.ACTIVE
    )

    _, session_analyst = auth_service.login("analyst_user", "PasswordAnalyst123!")
    _, session_viewer = auth_service.login("viewer_user", "PasswordViewer123!")

    article_repo = ArticleRepository(mock_db)
    now = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)

    # Seed Article 1: Canonical Reuters report
    art1, _ = article_repo.save_article_with_version(
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/news/reuters-energy",
        original_url="https://aljazeera.net/news/reuters-energy",
        resolved_url="https://aljazeera.net/news/reuters-energy",
        title="رويترز: اتفاق على رفع أسعار الغاز الطبيعي",
        body_text="رويترز - أعلنت الشركات الدولية في قطاع الطاقة التوصل لاتفاق لرفع أسعار الغاز.",
        published_at=now,
    )

    # Seed Article 2: Duplicate syndication published 30 mins later
    art2, _ = article_repo.save_article_with_version(
        source_id="alarabiya_ar",
        canonical_url="https://alarabiya.net/news/reuters-energy-copy",
        original_url="https://alarabiya.net/news/reuters-energy-copy",
        resolved_url="https://alarabiya.net/news/reuters-energy-copy",
        title="اتفاق لرفع أسعار الغاز وفق رويترز",
        body_text="رويترز - أعلنت الشركات الدولية في قطاع الطاقة التوصل لاتفاق لرفع أسعار الغاز.",
        published_at=now + timedelta(minutes=30),
    )

    return {
        "client": client,
        "db": mock_db,
        "token_analyst": session_analyst.session_token,
        "token_viewer": session_viewer.session_token,
        "art1_id": art1.article_id,
        "art2_id": art2.article_id,
    }


def test_service_deduplicate_and_replay_idempotency(dedup_env):
    """Test DeduplicationService execution and that re-running is idempotent."""
    db = dedup_env["db"]
    service = DeduplicationService(db)
    art2_id = dedup_env["art2_id"]

    # First run
    rels = service.deduplicate_article(art2_id)
    assert len(rels) == 1
    rel = rels[0]
    assert rel.canonical_article_id == dedup_env["art1_id"]
    assert rel.duplicate_article_id == art2_id
    assert rel.duplicate_type == DuplicateType.SYNDICATION

    # Verify duplicate repository count
    dup_repo = DuplicateRepository(db)
    all_rels = dup_repo.get_duplicates_for_article(art2_id)
    assert len(all_rels) == 1

    # Second run (replaying deduplication must be idempotent)
    rels_replay = service.deduplicate_article(art2_id)
    assert len(rels_replay) == 1
    all_rels_after = dup_repo.get_duplicates_for_article(art2_id)
    assert len(all_rels_after) == 1, "Idempotency violated: duplicate relationships were created!"


def test_api_deduplicate_and_get_duplicates(dedup_env):
    client = dedup_env["client"]
    token_analyst = dedup_env["token_analyst"]
    token_viewer = dedup_env["token_viewer"]
    art1_id = dedup_env["art1_id"]
    art2_id = dedup_env["art2_id"]

    headers_analyst = {"Authorization": f"Bearer {token_analyst}"}
    headers_viewer = {"Authorization": f"Bearer {token_viewer}"}

    # 1. Viewer trying to trigger deduplication should get 403 (Analyst/Admin required)
    res_forbidden = client.post(f"/api/articles/{art2_id}/deduplicate", headers=headers_viewer)
    assert res_forbidden.status_code == 403

    # 2. Analyst triggers deduplication
    res_dedup = client.post(f"/api/articles/{art2_id}/deduplicate", headers=headers_analyst)
    assert res_dedup.status_code == 200
    data = res_dedup.json()
    assert len(data) == 1
    assert data[0]["is_canonical"] is False
    assert data[0]["duplicate_type"] == "syndication"
    assert data[0]["related_article"]["article_id"] == art1_id
    # Crucial memory defense: body_text must NOT be present in preview
    assert "body_text" not in data[0]["related_article"]

    # 3. Viewer can view duplicates via GET
    res_get = client.get(f"/api/articles/{art1_id}/duplicates", headers=headers_viewer)
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert len(data_get) == 1
    assert data_get[0]["is_canonical"] is True
    assert data_get[0]["related_article"]["article_id"] == art2_id

    # 4. Unknown article 404
    res_404 = client.get("/api/articles/nonexistent-id/duplicates", headers=headers_viewer)
    assert res_404.status_code == 404
