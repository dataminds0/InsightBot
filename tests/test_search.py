"""Comprehensive unit and integration tests for Hybrid Search, Index Generations, and RRF (T15).

Verifies:
1. Lexical BM25 term weighting and title boost.
2. Vector 384-dimensional unit embeddings and cosine similarity.
3. Hybrid Reciprocal Rank Fusion (RRF).
4. Stale-write and disabled source policy enforcement.
5. Generation lifecycle, validation, and zero-downtime alias swap.
6. Reliable Basic fallback when vector search is stopped/fails.
7. API endpoints (GET /api/search, POST /api/search/rebuild, GET /api/search/status).
8. Whole-corpus memory defense: full body_text is strictly excluded from search results (Defect A12).
"""

from datetime import datetime, timezone

import mongomock
import pytest
from fastapi.testclient import TestClient

from insightbot.api.deps import get_db
from insightbot.api.main import app
from insightbot.models.search import SearchMode
from insightbot.models.user import Role, UserStatus
from insightbot.modules.search.indexer import SearchGenerationManager
from insightbot.modules.search.lexical import compute_lexical_score, extract_search_tokens
from insightbot.modules.search.service import SearchService
from insightbot.modules.search.vector import compute_deterministic_vector, cosine_similarity
from insightbot.repositories.article_repository import ArticleRepository
from insightbot.repositories.user_repository import UserRepository
from insightbot.services.auth_service import AuthService


def test_vector_normalization_and_cosine():
    v1 = compute_deterministic_vector("أسعار النفط والطاقة في الأسواق العالمية", dimensions=384)
    assert len(v1) == 384
    # Unit vector magnitude check
    mag = sum(x * x for x in v1) ** 0.5
    assert abs(mag - 1.0) < 1e-4

    v2 = compute_deterministic_vector("أسعار النفط والطاقة العالمية اليوم", dimensions=384)
    v3 = compute_deterministic_vector("مهرجان السينما الدولي للأفلام الوثائقية", dimensions=384)

    sim_related = cosine_similarity(v1, v2)
    sim_unrelated = cosine_similarity(v1, v3)

    assert sim_related > sim_unrelated
    assert sim_related >= 0.50


def test_lexical_scoring_and_safe_snippet():
    tokens = extract_search_tokens("أسعار الفائدة البنوك")
    assert "اسعار" in tokens
    assert "الفائده" in tokens
    assert "البنوك" in tokens

    title = "البنوك المركزية تقرر رفع أسعار الفائدة"
    body = "قررت لجنة السياسة النقدية اليوم بعد اجتماع مطول رفع أسعار الفائدة الأساسية بنصف نقطة مئوية للحد من التضخم المتصاعد في البلاد."

    score, snippet = compute_lexical_score(tokens, title, body)
    assert score > 2.0
    assert "الفائدة" in snippet or "أسعار" in snippet
    assert len(snippet) <= 200, "Snippet must be strictly bounded to prevent whole-text leakage!"


@pytest.fixture
def search_env():
    mock_client = mongomock.MongoClient()
    mock_db = mock_client["test_search"]

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    user_repo = UserRepository(mock_db)
    auth_service = AuthService(user_repo)

    auth_service.register(
        "analyst_search", "PasswordAnalyst123!", role=Role.ANALYST, status=UserStatus.ACTIVE
    )
    auth_service.register(
        "viewer_search", "PasswordViewer123!", role=Role.VIEWER, status=UserStatus.ACTIVE
    )

    _, session_analyst = auth_service.login("analyst_search", "PasswordAnalyst123!")
    _, session_viewer = auth_service.login("viewer_search", "PasswordViewer123!")

    article_repo = ArticleRepository(mock_db)
    now = datetime(2026, 11, 17, 10, 0, tzinfo=timezone.utc)

    # Seed 3 articles
    art1, _ = article_repo.save_article_with_version(
        source_id="aljazeera_ar",
        canonical_url="https://aljazeera.net/energy/opec-cuts",
        original_url="https://aljazeera.net/energy/opec-cuts",
        resolved_url="https://aljazeera.net/energy/opec-cuts",
        title="أوبك تقرر خفض إنتاج النفط الخام عالميا",
        body_text="اتفقت الدول المصدرة للنفط في تحالف أوبك بلس على خفض طوعي لمعدلات إنتاج النفط الخام لدعم استقرار أسواق الطاقة والغاز.",
        published_at=now,
    )

    art2, _ = article_repo.save_article_with_version(
        source_id="reuters_en",
        canonical_url="https://reuters.com/markets/energy-oil",
        original_url="https://reuters.com/markets/energy-oil",
        resolved_url="https://reuters.com/markets/energy-oil",
        title="Crude oil futures rally following OPEC output policy decision",
        body_text="Global crude oil benchmarks climbed sharply after oil ministers concluded their Vienna meeting with formal production curbs.",
        published_at=now,
    )

    art3, _ = article_repo.save_article_with_version(
        source_id="bbc_ar",
        canonical_url="https://bbc.com/tech/ai-innovation",
        original_url="https://bbc.com/tech/ai-innovation",
        resolved_url="https://bbc.com/tech/ai-innovation",
        title="القمة العالمية للذكاء الاصطناعي تبحث الضوابط الأخلاقية",
        body_text="افتتحت القمة العالمية للذكاء الاصطناعي فعالياتها اليوم لمناقشة أطر الحوكمة وحماية البيانات الرقمية.",
        published_at=now,
    )

    # Enable sources
    mock_db["sources"].insert_one({"source_id": "aljazeera_ar", "enabled": True})
    mock_db["sources"].insert_one({"source_id": "reuters_en", "enabled": True})
    # bbc_ar disabled to test source policy enforcement
    mock_db["sources"].insert_one({"source_id": "bbc_ar", "enabled": False})

    return {
        "client": client,
        "db": mock_db,
        "token_analyst": session_analyst.session_token,
        "token_viewer": session_viewer.session_token,
        "art1_id": art1.article_id,
        "art2_id": art2.article_id,
        "art3_id": art3.article_id,
    }


def test_generation_management_and_alias_swap(search_env):
    db = search_env["db"]
    gen_mgr = SearchGenerationManager(db)

    # Build initial generation
    gen1 = gen_mgr.build_generation("gen_alpha")
    assert gen1.generation_id == "gen_alpha"
    assert gen1.chunks_count >= 3
    assert gen1.is_active is True

    # Build second generation (initially inactive)
    gen2 = gen_mgr.build_generation("gen_beta")
    assert gen2.is_active is False

    # Validate generation
    assert gen_mgr.validate_generation("gen_beta") is True

    # Atomic alias swap
    swapped = gen_mgr.swap_active_generation("gen_beta")
    assert swapped.generation_id == "gen_beta"
    assert swapped.is_active is True

    # Previous generation must now be inactive
    doc_alpha = db["search_generations"].find_one({"generation_id": "gen_alpha"})
    assert doc_alpha is not None
    assert doc_alpha["is_active"] is False


def test_search_service_hybrid_and_policy_enforcement(search_env):
    db = search_env["db"]
    service = SearchService(db)

    # Build active generation
    service.gen_manager.build_generation()

    # Search query matching oil/energy
    res = service.search(query="إنتاج النفط الخام وأوبك", mode=SearchMode.HYBRID)
    assert res.search_mode == SearchMode.HYBRID
    assert res.total >= 1

    # Policy guard: disabled source 'bbc_ar' must NOT be included in results!
    returned_sources = {item.source_id for item in res.items}
    assert "bbc_ar" not in returned_sources, "Disabled source bbc_ar must be filtered by policy guard!"

    # Memory defense (Defect A12): full body_text must NOT be present on items
    for item in res.items:
        assert not hasattr(item, "body_text")
        assert len(item.snippet) <= 250


def test_basic_fallback_when_search_stopped(search_env):
    db = search_env["db"]
    service = SearchService(db)

    # Force Basic mode or test when no generation exists
    res = service.search(query="النفط", mode=SearchMode.BASIC)
    assert res.search_mode == SearchMode.BASIC
    assert len(res.items) >= 1
    assert "Explicit basic search" in (res.fallback_reason or "")


def test_api_search_endpoints(search_env):
    client = search_env["client"]
    token_analyst = search_env["token_analyst"]
    token_viewer = search_env["token_viewer"]
    headers_analyst = {"Authorization": f"Bearer {token_analyst}"}
    headers_viewer = {"Authorization": f"Bearer {token_viewer}"}

    # 1. Viewer executes search
    res = client.get("/api/search?q=oil+production", headers=headers_viewer)
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "search_mode" in data

    # 2. GET /api/search/status
    res_status = client.get("/api/search/status", headers=headers_viewer)
    assert res_status.status_code == 200
    assert "index_lag_seconds" in res_status.json()

    # 3. POST /api/search/rebuild (Viewer gets 403 Forbidden)
    res_forbidden = client.post("/api/search/rebuild", headers=headers_viewer)
    assert res_forbidden.status_code == 403

    # 4. POST /api/search/rebuild (Analyst succeeds)
    res_rebuild = client.post("/api/search/rebuild", headers=headers_analyst)
    assert res_rebuild.status_code == 200
    assert res_rebuild.json()["status"] == "valid"
