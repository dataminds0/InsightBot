"""Tests for Task T24: Legacy CSV inventory, safe transformation, migration, and account review."""

from pathlib import Path

import mongomock
import pytest

from insightbot.modules.operations.migration import (
    LegacyMigrationService,
    parse_iso_datetime,
)


@pytest.fixture
def sample_legacy_csv(tmp_path: Path) -> Path:
    """Create a temporary legacy CSV file simulating historical news collection."""
    csv_file = tmp_path / "legacy_data.csv"
    csv_content = (
        "id,source,url,title,published_at,fetched_at,t_total_sec,content,h1\n"
        "1,cnn,https://edition.cnn.com/2025/09/09/world/article-1,خبر عالمي أول,2025-09-09T13:14:58Z,2025-09-09T21:22:01Z,1.2,تفاصيل موسعة للخبر العالمي الأول مع تحليل عميق للأحداث الميدانية والبيانات السياسية والدبلوماسية في المنطقة.,خبر عالمي أول\n"
        "2,bbc,https://www.bbc.com/arabic/article-2,خبر باللغة العربية بدون تاريخ نشر,,2025-09-09T21:25:00Z,0.8,موجز قصير للخبر,خبر باللغة العربية\n"
        "3,cnn,https://edition.cnn.com/2025/09/09/world/article-1,عنوان مكرر لنفس الرابط,2025-09-09T13:14:58Z,2025-09-09T21:30:00Z,1.0,نفس النص المكرر,عنوان مكرر\n"
    )
    csv_file.write_text(csv_content, encoding="utf-8")
    return csv_file


def test_parse_iso_datetime() -> None:
    """Verify safe ISO datetime parsing into UTC timezone-aware datetimes."""
    assert parse_iso_datetime(None) is None
    assert parse_iso_datetime("") is None
    assert parse_iso_datetime("invalid-date") is None

    dt = parse_iso_datetime("2025-09-09T13:14:58Z")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 9
    assert dt.day == 9
    assert dt.hour == 13
    assert dt.minute == 14
    assert dt.second == 58


def test_scan_legacy_inventory(sample_legacy_csv: Path) -> None:
    """Verify inventory scanning without modifying database."""
    client = mongomock.MongoClient()
    db = client["test_migration"]
    service = LegacyMigrationService(db)

    inventory = service.scan_inventory(sample_legacy_csv)
    assert inventory.total_rows == 3
    assert inventory.unique_urls == 2
    assert inventory.duplicate_urls == 1
    assert inventory.sources_distribution["cnn"] == 2
    assert inventory.sources_distribution["bbc"] == 1
    assert inventory.valid_publication_dates == 2
    assert inventory.missing_publication_dates == 1
    assert inventory.average_word_count > 0.0


def test_legacy_migration_dry_run_safety(sample_legacy_csv: Path) -> None:
    """Verify dry-run migration performs full simulation without writing to database."""
    client = mongomock.MongoClient()
    db = client["test_migration"]
    service = LegacyMigrationService(db)

    report = service.migrate_legacy_csv(sample_legacy_csv, dry_run=True)
    assert report.dry_run is True
    assert report.migrated_articles_count == 2  # 2 unique URLs
    assert report.unknown_dates_handled == 1  # 1 missing date
    assert report.passed_gate is True

    # Ensure zero documents were written in dry run
    assert db["articles"].count_documents({}) == 0
    assert db["article_revisions"].count_documents({}) == 0


def test_legacy_migration_execution_and_defect_a13_preservation(
    sample_legacy_csv: Path,
) -> None:
    """
    Verify actual migration transforms legacy CSV records, derives deterministic IDs,
    preserves numeric legacy IDs, maps unknown dates safely (Defect A13),
    and records first_seen_basis=imported.
    """
    client = mongomock.MongoClient()
    db = client["test_migration"]
    service = LegacyMigrationService(db)

    # 1. First execution
    report = service.migrate_legacy_csv(
        sample_legacy_csv, dry_run=False, operator_username="analyst_1"
    )
    assert report.dry_run is False
    assert report.migrated_articles_count == 2
    assert report.migrated_revisions_count == 2
    assert report.collisions_skipped == 1  # 1 duplicate in CSV

    assert db["articles"].count_documents({}) == 2
    assert db["article_revisions"].count_documents({}) == 2

    # Check article with missing date (Defect A13)
    art_no_date = db["articles"].find_one({"source_id": "legacy_bbc"})
    assert art_no_date is not None
    assert art_no_date["published_at"] is None
    assert art_no_date["publication_date_unknown_reason"] == "legacy_unspecified_date"
    assert art_no_date["extra_metadata"]["legacy_id"] == "2"
    assert art_no_date["extra_metadata"]["first_seen_basis"] == "imported"
    assert art_no_date["extra_metadata"]["legacy_summary_only"] is True  # Brief summary < 30 words

    # Check article with valid date
    art_with_date = db["articles"].find_one({"source_id": "legacy_cnn"})
    assert art_with_date is not None
    assert art_with_date["published_at"] is not None
    assert art_with_date["extra_metadata"]["legacy_id"] == "1"

    # 2. Re-run idempotency & collision test
    rerun_report = service.migrate_legacy_csv(sample_legacy_csv, dry_run=False)
    assert rerun_report.migrated_articles_count == 0  # None migrated
    assert rerun_report.collisions_skipped == 3  # All existing URLs skipped
    assert db["articles"].count_documents({}) == 2  # No duplication


def test_review_seeded_accounts() -> None:
    """Verify review_seeded_accounts flags suspicious accounts without deleting them."""
    client = mongomock.MongoClient()
    db = client["test_migration"]

    db["users"].insert_many(
        [
            {
                "user_id": "u1",
                "username": "admin",
                "email": "admin@example.com",
                "role": "admin",
                "password_hash": "$2b$12$legacyBcryptHash...",
            },
            {
                "user_id": "u2",
                "username": "legit_analyst",
                "email": "analyst@organization.org",
                "role": "analyst",
                "password_hash": "$argon2id$v=19$m=65536,t=3,p=4$...",
            },
        ]
    )

    service = LegacyMigrationService(db)
    suspects = service.review_seeded_accounts()

    assert len(suspects) == 1
    assert suspects[0]["username"] == "admin"
    assert any("example.com" in r for r in suspects[0]["reasons"])
    assert "Manual analyst verification" in suspects[0]["recommended_action"]
    # Verify account was NOT deleted
    assert db["users"].count_documents({}) == 2
