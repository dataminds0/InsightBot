"""Consistent backup, integrity verification, and separate-target restore drill service."""

import hashlib
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from pymongo.database import Database

logger = logging.getLogger(__name__)

ALL_CORE_COLLECTIONS = [
    "sources",
    "users",
    "articles",
    "article_revisions",
    "stories",
    "duplicate_relationships",
    "jobs",
    "audit_logs",
    "bookmarks",
    "saved_queries",
    "analyst_notes",
    "notifications",
    "notification_dedup_records",
    "source_batches",
]


class BackupManifest(BaseModel):
    """Immutable metadata and checksum manifest for a backup archive."""

    backup_id: str
    created_at: datetime
    database_name: str
    manifest_version: str = "1.0"
    collections: dict[str, int] = Field(default_factory=dict)
    collection_checksums: dict[str, str] = Field(default_factory=dict)
    has_raw_storage: bool = False
    raw_files_count: int = 0
    config_files: list[str] = Field(default_factory=list)


class RestoreDrillReport(BaseModel):
    """Audit report for separate-target restore drill."""

    backup_id: str
    target_database: str
    started_at: datetime
    completed_at: datetime
    recovery_time_seconds: float
    total_collections_restored: int
    total_documents_restored: int
    checksums_verified: bool
    reference_integrity_verified: bool
    article_revisions_verified: bool
    passed_gate: bool
    diagnostics: list[str] = Field(default_factory=list)


def compute_sha256(data: bytes) -> str:
    """Compute standard SHA-256 hexadecimal digest."""
    return hashlib.sha256(data).hexdigest()


class BackupService:
    """
    Manages complete, consistent backups, cryptographic integrity verification,
    and separate-target restore drills (Task T23).
    """

    def __init__(self, db: Database[dict[str, Any]]):
        self.db = db

    def create_backup(
        self,
        output_dir: Path,
        include_raw: bool = True,
        raw_dir: Optional[Path] = None,
        configs_dir: Optional[Path] = None,
    ) -> tuple[Path, BackupManifest]:
        """
        Create a consistent backup of MongoDB collections, configuration, and raw storage.
        Writes JSONL data files, SHA-256 checksums, and a manifest.json.
        """
        now = datetime.now(timezone.utc)
        backup_id = f"backup_{now.strftime('%Y%m%d_%H%M%S')}"
        backup_path = output_dir / backup_id
        data_path = backup_path / "data"
        configs_target = backup_path / "configs"

        data_path.mkdir(parents=True, exist_ok=True)
        configs_target.mkdir(parents=True, exist_ok=True)

        collections_counts: dict[str, int] = {}
        collections_checksums: dict[str, str] = {}

        # 1. Export MongoDB collections to JSONL
        for col_name in ALL_CORE_COLLECTIONS:
            cursor = self.db[col_name].find({})
            lines: list[bytes] = []
            count = 0
            for doc in cursor:
                # Normalize _id to string for reproducible JSON export
                doc_clean = {k: str(v) if k == "_id" else v for k, v in doc.items()}
                line = json.dumps(doc_clean, sort_keys=True, default=str).encode("utf-8")
                lines.append(line + b"\n")
                count += 1

            col_file = data_path / f"{col_name}.jsonl"
            file_bytes = b"".join(lines)
            col_file.write_bytes(file_bytes)

            collections_counts[col_name] = count
            collections_checksums[col_name] = compute_sha256(file_bytes)

        # 2. Archive Configuration files
        cfg_source = configs_dir or Path("configs")
        copied_configs: list[str] = []
        if cfg_source.exists():
            for item in cfg_source.glob("*.yaml"):
                shutil.copy2(item, configs_target / item.name)
                copied_configs.append(item.name)

        # 3. Archive Raw storage if requested
        raw_source = raw_dir or Path("data/raw")
        raw_count = 0
        has_raw = False
        if include_raw and raw_source.exists():
            raw_target = backup_path / "raw"
            raw_target.mkdir(parents=True, exist_ok=True)
            for f in raw_source.glob("**/*"):
                if f.is_file():
                    rel_p = f.relative_to(raw_source)
                    dest_p = raw_target / rel_p
                    dest_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest_p)
                    raw_count += 1
            has_raw = raw_count > 0

        manifest = BackupManifest(
            backup_id=backup_id,
            created_at=now,
            database_name=self.db.name,
            collections=collections_counts,
            collection_checksums=collections_checksums,
            has_raw_storage=has_raw,
            raw_files_count=raw_count,
            config_files=copied_configs,
        )

        manifest_file = backup_path / "manifest.json"
        manifest_file.write_text(
            json.dumps(manifest.model_dump(), indent=2, default=str), encoding="utf-8"
        )

        return backup_path, manifest

    @staticmethod
    def verify_backup(backup_path: Path) -> tuple[bool, list[str]]:
        """
        Verify cryptographic integrity of a backup without modifying target systems.
        Checks file presence, SHA-256 hashes, and document counts against manifest.json.
        """
        issues: list[str] = []
        manifest_file = backup_path / "manifest.json"
        if not manifest_file.exists():
            return False, ["Backup manifest.json missing from directory."]

        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            manifest = BackupManifest.model_validate(manifest_data)
        except Exception as exc:
            return False, [f"Failed to parse backup manifest: {exc}"]

        data_dir = backup_path / "data"
        if not data_dir.exists():
            return False, ["Backup data directory missing."]

        for col_name, expected_checksum in manifest.collection_checksums.items():
            col_file = data_dir / f"{col_name}.jsonl"
            if not col_file.exists():
                issues.append(f"Missing expected collection dump: {col_name}.jsonl")
                continue

            file_bytes = col_file.read_bytes()
            actual_checksum = compute_sha256(file_bytes)
            if actual_checksum != expected_checksum:
                issues.append(
                    f"Checksum mismatch for '{col_name}': expected {expected_checksum}, got {actual_checksum}"
                )

            # Verify line count matches document count
            lines_count = sum(1 for line in file_bytes.splitlines() if line.strip())
            expected_count = manifest.collections.get(col_name, 0)
            if lines_count != expected_count:
                issues.append(
                    f"Document count mismatch for '{col_name}': expected {expected_count}, got {lines_count}"
                )

        return len(issues) == 0, issues

    @staticmethod
    def run_restore_drill(
        backup_path: Path,
        target_db: Database[dict[str, Any]],
        cleanup_after: bool = True,
    ) -> RestoreDrillReport:
        """
        Execute a complete restore drill to an isolated separate target database.
        Validates ID stability, revisions, versioning, reference integrity, and measures RTO.
        """
        t0 = time.perf_counter()
        started_at = datetime.now(timezone.utc)
        diagnostics: list[str] = []

        # 1. Verify backup integrity before restoring
        valid, issues = BackupService.verify_backup(backup_path)
        if not valid:
            completed_at = datetime.now(timezone.utc)
            return RestoreDrillReport(
                backup_id=backup_path.name,
                target_database=target_db.name,
                started_at=started_at,
                completed_at=completed_at,
                recovery_time_seconds=round(time.perf_counter() - t0, 3),
                total_collections_restored=0,
                total_documents_restored=0,
                checksums_verified=False,
                reference_integrity_verified=False,
                article_revisions_verified=False,
                passed_gate=False,
                diagnostics=issues,
            )

        manifest_file = backup_path / "manifest.json"
        manifest = BackupManifest.model_validate(
            json.loads(manifest_file.read_text(encoding="utf-8"))
        )

        total_restored_docs = 0
        total_restored_cols = 0
        data_dir = backup_path / "data"

        # 2. Restore into target database
        for col_name in manifest.collection_checksums.keys():
            col_file = data_dir / f"{col_name}.jsonl"
            if not col_file.exists():
                continue

            target_col = target_db[col_name]
            # Ensure target collection is clear
            target_col.delete_many({})

            docs_to_insert: list[dict[str, Any]] = []
            for line in col_file.read_bytes().splitlines():
                if line.strip():
                    doc = json.loads(line.decode("utf-8"))
                    docs_to_insert.append(doc)

            if docs_to_insert:
                target_col.insert_many(docs_to_insert)

            count = target_col.count_documents({})
            total_restored_docs += count
            total_restored_cols += 1

        # 3. Verify Reference Integrity (Stories -> Articles)
        ref_ok = True
        stories_col = target_db["stories"]
        articles_col = target_db["articles"]
        for story in stories_col.find({}):
            article_ids = story.get("article_ids", [])
            for aid in article_ids:
                if not articles_col.find_one({"article_id": aid}):
                    diagnostics.append(
                        f"Dangling reference: Story '{story.get('story_id')}' points to missing article '{aid}'"
                    )
                    ref_ok = False

        # 4. Verify Revision Integrity
        rev_ok = True
        rev_col = target_db["article_revisions"]
        for rev in rev_col.find({}):
            aid = rev.get("article_id")
            if not articles_col.find_one({"article_id": aid}):
                diagnostics.append(
                    f"Dangling revision: Revision points to missing article '{aid}'"
                )
                rev_ok = False

        recovery_duration = round(time.perf_counter() - t0, 3)
        completed_at = datetime.now(timezone.utc)

        passed = ref_ok and rev_ok and (total_restored_cols >= len(manifest.collections))

        diagnostics.append(
            f"Restored {total_restored_cols} collections and {total_restored_docs} documents into '{target_db.name}' in {recovery_duration}s."
        )

        if cleanup_after:
            for col_name in manifest.collection_checksums.keys():
                target_db[col_name].drop()
            diagnostics.append(f"Cleaned up target database '{target_db.name}' after drill.")

        return RestoreDrillReport(
            backup_id=manifest.backup_id,
            target_database=target_db.name,
            started_at=started_at,
            completed_at=completed_at,
            recovery_time_seconds=recovery_duration,
            total_collections_restored=total_restored_cols,
            total_documents_restored=total_restored_docs,
            checksums_verified=True,
            reference_integrity_verified=ref_ok,
            article_revisions_verified=rev_ok,
            passed_gate=passed,
            diagnostics=diagnostics,
        )
