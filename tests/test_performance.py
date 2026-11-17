"""Tests for Task T22: Performance, benchmarking, and source expansion batches."""

import sys
from pathlib import Path

import mongomock

from insightbot.models.source import Source
from insightbot.modules.operations.benchmark import (
    calculate_percentiles,
    get_hardware_profile,
    measure_projection_efficiency,
    measure_query_latency,
)
from insightbot.modules.sources.batches import (
    SourceBatch,
    SourceBatchManager,
    SourceBatchStatus,
)
from insightbot.repositories.source_repository import SourceRepository


def test_hardware_profiling() -> None:
    """Verify hardware profile collects valid system attributes."""
    profile = get_hardware_profile()
    assert profile.cpu_count >= 1
    assert profile.total_ram_gb > 0.0
    assert profile.available_ram_gb >= 0.0
    assert profile.disk_total_gb > 0.0
    assert profile.disk_free_gb >= 0.0
    assert profile.platform_system in ["Windows", "Linux", "Darwin"]
    assert profile.python_version.startswith(f"{sys.version_info.major}.{sys.version_info.minor}")


def test_percentile_calculations() -> None:
    """Verify statistical percentile calculations for latency measurements."""
    # Test empty latency list
    empty_stats = calculate_percentiles([], 1.0)
    assert empty_stats.p50_ms == 0.0
    assert empty_stats.total_samples == 0

    # Test distribution from 1ms to 100ms (100 samples)
    latencies = [float(i) for i in range(1, 101)]
    stats = calculate_percentiles(latencies, duration_sec=0.5)

    assert stats.total_samples == 100
    assert stats.min_ms == 1.0
    assert stats.max_ms == 100.0
    assert 49.0 <= stats.p50_ms <= 51.0
    assert 94.0 <= stats.p95_ms <= 96.0
    assert 98.0 <= stats.p99_ms <= 100.0
    assert stats.qps == 200.0  # 100 samples / 0.5 sec


def test_projection_efficiency_defect_a12_defense() -> None:
    """
    Verify projection of {"body_text": 0} provides >= 80% payload reduction,
    safeguarding system against memory exhaustion (Defect A12).
    """
    client = mongomock.MongoClient()
    db = client["insightbot_test"]
    articles_col = db["articles"]

    # Insert 10 mock articles with substantial body_text
    for i in range(10):
        articles_col.insert_one(
            {
                "article_id": f"art_{i}",
                "url": f"https://example.com/article/{i}",
                "title": f"عنوان المقال الإخباري التجريبي رقم {i}",
                "body_text": "هذا نص إخباري طويل جداً يحتوي على تفاصيل دقيقة للأحداث والبيانات " * 150,
                "language": "ar",
                "source_id": "test_src",
                "fetched_at": "2026-11-17T12:00:00Z",
            }
        )

    res = measure_projection_efficiency(db, sample_limit=10)
    assert res.sample_count == 10
    assert res.full_payload_bytes > res.projected_payload_bytes
    assert res.reduction_pct >= 80.0
    assert res.passed_gate is True


def test_query_latency_concurrency_gate() -> None:
    """Verify concurrent query runner against simulated MongoDB collection."""
    client = mongomock.MongoClient()
    db = client["insightbot_test"]
    articles_col = db["articles"]

    for i in range(25):
        articles_col.insert_one(
            {
                "article_id": f"art_{i}",
                "title": f"Title {i}",
                "body_text": "Body content " * 50,
                "published_at": "2026-11-17T12:00:00Z",
            }
        )

    stats = measure_query_latency(db, concurrency=4, total_requests=20)
    assert stats.total_samples == 20
    assert stats.p95_ms < 1000.0  # Gate: List p95 < 1.0s


def test_source_expansion_batch_lifecycle_and_reversibility() -> None:
    """
    Verify source expansion batch activation and reversible rollback.
    Operators can roll back an entire batch atomically without collateral damage.
    """
    client = mongomock.MongoClient()
    db = client["insightbot_test"]
    source_repo = SourceRepository(db)

    # Setup 2 sources belonging to an expansion batch, initially disabled
    src1 = Source(
        source_id="expansion_mena_01",
        name="MENA News 1",
        url="https://mena1.example.com",
        language="ar",
        enabled=False,
    )
    src2 = Source(
        source_id="expansion_mena_02",
        name="MENA News 2",
        url="https://mena2.example.com",
        language="ar",
        enabled=False,
    )
    source_repo.upsert_source(src1)
    source_repo.upsert_source(src2)

    manager = SourceBatchManager(db)
    batch = SourceBatch(
        batch_id="batch_mena_2026",
        name="MENA Expansion Batch Q4",
        description="Reviewed MENA regional news sources",
        source_ids=["expansion_mena_01", "expansion_mena_02"],
        review_signoff_by="lead_analyst",
    )
    manager.register_batch(batch)

    # 1. Activation Phase
    activated_count = manager.activate_batch("batch_mena_2026", operator_username="analyst_user")
    assert activated_count == 2

    # Verify both sources are now enabled
    assert source_repo.get_by_id("expansion_mena_01").enabled is True
    assert source_repo.get_by_id("expansion_mena_02").enabled is True

    updated_batch = manager.get_batch("batch_mena_2026")
    assert updated_batch is not None
    assert updated_batch.status == SourceBatchStatus.ACTIVE
    assert updated_batch.activated_at is not None

    # 2. Reversible Rollback Phase
    rollback_count = manager.rollback_batch(
        "batch_mena_2026",
        operator_username="analyst_user",
        reason="Upstream 429 rate-limiting and formatting regressions",
    )
    assert rollback_count == 2

    # Verify both sources were atomically disabled
    assert source_repo.get_by_id("expansion_mena_01").enabled is False
    assert source_repo.get_by_id("expansion_mena_02").enabled is False

    rolled_back_batch = manager.get_batch("batch_mena_2026")
    assert rolled_back_batch is not None
    assert rolled_back_batch.status == SourceBatchStatus.ROLLED_BACK
    assert rolled_back_batch.rolled_back_at is not None
    assert "429" in (rolled_back_batch.rollback_reason or "")


def test_adr_crawler_and_infrastructure_performance_exists() -> None:
    """Verify that ADR-0001 exists, is Accepted, and documents objective triggers."""
    adr_path = Path("docs/adr/0001_crawler_and_infrastructure_performance.md")
    assert adr_path.exists(), "ADR-0001 file does not exist!"

    content = adr_path.read_text(encoding="utf-8")
    assert "ADR 0001" in content
    assert "Status:** Accepted" in content or "Status: Accepted" in content
    assert "HTTPX" in content
    assert "Trafilatura" in content
    assert "Reversal Triggers" in content
