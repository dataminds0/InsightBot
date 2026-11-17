"""Tests for Task T23: Consistent backups, cryptographic verification, restore drills, and retention."""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mongomock
import pytest

from insightbot.modules.operations.backup import (
    BackupService,
)
from insightbot.modules.operations.retention import RetentionPolicyService


@pytest.fixture
def populated_mock_db() -> mongomock.Database:
    """Prepare an isolated mock MongoDB database with populated domain entities."""
    client = mongomock.MongoClient()
    db = client["insightbot_backup_test"]

    # 1. Sources
    db["sources"].insert_one(
        {
            "source_id": "test_src_1",
            "name": "Test Source 1",
            "url": "https://example.com",
            "language": "ar",
            "enabled": True,
            "policy": {"rate_limit_per_minute": 20, "retention_days": 30},
        }
    )

    # 2. Articles
    db["articles"].insert_many(
        [
            {
                "article_id": "art_101",
                "source_id": "test_src_1",
                "url": "https://example.com/101",
                "title": "مقال تجريبي أول",
                "body_text": "نص المقال الإخباري الأول الموثق",
                "language": "ar",
                "published_at": "2026-11-17T10:00:00Z",
                "fetched_at": "2026-11-17T10:05:00Z",
            },
            {
                "article_id": "art_102",
                "source_id": "test_src_1",
                "url": "https://example.com/102",
                "title": "مقال تجريبي ثان",
                "body_text": "نص المقال الإخباري الثاني الموثق",
                "language": "ar",
                "published_at": "2026-11-17T11:00:00Z",
                "fetched_at": "2026-11-17T11:05:00Z",
            },
        ]
    )

    # 3. Article Revisions
    db["article_revisions"].insert_one(
        {
            "article_id": "art_101",
            "version": 1,
            "title": "مقال تجريبي أول - مسودة",
            "body_text": "نص مبكر",
            "created_at": "2026-11-17T09:00:00Z",
        }
    )

    # 4. Stories
    db["stories"].insert_one(
        {
            "story_id": "story_01",
            "title": "تغطية الحدث التجريبي",
            "article_ids": ["art_101", "art_102"],
            "version": 1,
            "status": "peak",
            "created_at": "2026-11-17T12:00:00Z",
        }
    )

    # 5. Audit Logs
    db["audit_logs"].insert_one(
        {
            "actor_id": "admin",
            "action": "system_bootstrap",
            "entity_type": "system",
            "entity_id": "init",
            "created_at": "2026-11-17T08:00:00Z",
        }
    )

    # 6. Jobs
    db["jobs"].insert_one(
        {
            "job_id": "job_01",
            "job_type": "ingest",
            "target_id": "test_src_1",
            "status": "completed",
            "updated_at": datetime.now(timezone.utc) - timedelta(days=45),
        }
    )

    return db


def test_backup_creation_and_integrity_verification(
    tmp_path: Path, populated_mock_db: mongomock.Database
) -> None:
    """Verify consistent backup generation and cryptographic checksum verification."""
    svc = BackupService(populated_mock_db)

    # Setup dummy raw storage & configs
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "article_raw_1.html").write_text("<html>Raw HTML</html>", encoding="utf-8")

    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "sources.yaml").write_text("sources: []", encoding="utf-8")

    backup_path, manifest = svc.create_backup(
        output_dir=tmp_path / "backups",
        include_raw=True,
        raw_dir=raw_dir,
        configs_dir=cfg_dir,
    )

    assert backup_path.exists()
    assert (backup_path / "manifest.json").exists()
    assert manifest.database_name == populated_mock_db.name
    assert manifest.collections["articles"] == 2
    assert manifest.collections["stories"] == 1
    assert manifest.collections["article_revisions"] == 1
    assert manifest.has_raw_storage is True
    assert manifest.raw_files_count == 1
    assert "sources.yaml" in manifest.config_files

    # Verification of pristine backup
    valid, issues = BackupService.verify_backup(backup_path)
    assert valid is True
    assert len(issues) == 0

    # Tampering test: tamper with one file and ensure verification fails
    articles_dump = backup_path / "data" / "articles.jsonl"
    articles_dump.write_text("tampered data\n", encoding="utf-8")

    valid_tampered, tampered_issues = BackupService.verify_backup(backup_path)
    assert valid_tampered is False
    assert any("Checksum mismatch" in iss for iss in tampered_issues)


def test_separate_target_restore_drill(
    tmp_path: Path, populated_mock_db: mongomock.Database
) -> None:
    """
    Verify complete separate-target restore drill.
    Ensures that articles, revisions, story references, and checksums are 100% verified.
    """
    svc = BackupService(populated_mock_db)
    backup_path, manifest = svc.create_backup(output_dir=tmp_path / "backups", include_raw=False)

    # Create distinct isolated drill target database
    client = mongomock.MongoClient()
    drill_db = client["insightbot_isolated_drill_target"]

    # Run restore drill without cleanup to inspect restored entities
    report = BackupService.run_restore_drill(backup_path, drill_db, cleanup_after=False)

    assert report.passed_gate is True
    assert report.checksums_verified is True
    assert report.reference_integrity_verified is True
    assert report.article_revisions_verified is True
    assert report.recovery_time_seconds < 10.0  # Well within the 4-hour RTO budget
    assert report.total_documents_restored >= 5

    # Check restored documents inside target database
    assert drill_db["articles"].count_documents({}) == 2
    assert drill_db["stories"].count_documents({}) == 1

    # Verify reference resolution: Story points to valid article
    restored_story = drill_db["stories"].find_one({"story_id": "story_01"})
    assert restored_story is not None
    for aid in restored_story["article_ids"]:
        assert drill_db["articles"].find_one({"article_id": aid}) is not None


def test_retention_policy_pruning_and_canonical_preservation(
    tmp_path: Path, populated_mock_db: mongomock.Database
) -> None:
    """
    Verify retention policy prunes transient raw files and old jobs while
    strictly preserving canonical articles, revisions, stories, and audit logs.
    """
    raw_dir = tmp_path / "raw"
    src_raw_dir = raw_dir / "test_src_1"
    src_raw_dir.mkdir(parents=True)

    # Create an old raw file (45 days old, exceeding test_src_1 30-day retention)
    old_file = src_raw_dir / "old_article.html"
    old_file.write_text("old html content", encoding="utf-8")
    old_timestamp = time.time() - (45 * 86400)
    import os

    os.utime(old_file, (old_timestamp, old_timestamp))

    # Create a recent raw file (2 days old)
    recent_file = src_raw_dir / "recent_article.html"
    recent_file.write_text("recent html content", encoding="utf-8")

    service = RetentionPolicyService(populated_mock_db, raw_storage_dir=raw_dir)

    # 1. Dry run test
    dry_result = service.prune_expired_data(default_retention_days=30, dry_run=True)
    assert dry_result.dry_run is True
    assert dry_result.raw_files_pruned == 1
    assert old_file.exists()  # dry-run does not delete!

    # 2. Actual execution
    exec_result = service.prune_expired_data(default_retention_days=30, dry_run=False)
    assert exec_result.dry_run is False
    assert exec_result.raw_files_pruned == 1
    assert not old_file.exists()  # Old file pruned
    assert recent_file.exists()  # Recent file retained

    # Verify transient jobs pruned
    assert exec_result.transient_jobs_pruned == 1
    assert populated_mock_db["jobs"].count_documents({}) == 0

    # CRITICAL: Verify canonical domain articles and audit logs are 100% preserved!
    assert populated_mock_db["articles"].count_documents({}) == 2
    assert populated_mock_db["article_revisions"].count_documents({}) == 1
    assert populated_mock_db["stories"].count_documents({}) == 1
    assert populated_mock_db["audit_logs"].count_documents({}) >= 1
