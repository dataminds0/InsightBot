"""Retention policy enforcement and storage pruning service."""

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from pymongo.database import Database

from insightbot.repositories.audit_repository import AuditRepository
from insightbot.repositories.source_repository import SourceRepository

logger = logging.getLogger(__name__)


class RetentionPruneResult(BaseModel):
    """Execution summary for retention policy pruning."""

    executed_at: datetime
    dry_run: bool
    raw_files_evaluated: int = 0
    raw_files_pruned: int = 0
    bytes_reclaimed: int = 0
    transient_jobs_pruned: int = 0
    canonical_articles_preserved: int = 0
    audit_logs_preserved: int = 0
    diagnostics: list[str] = Field(default_factory=list)


class RetentionPolicyService:
    """
    Enforces retention policies defined per source and cleans up transient raw files
    and old completed worker jobs, while strictly preserving canonical domain data.
    """

    def __init__(
        self,
        db: Database[dict[str, Any]],
        raw_storage_dir: Optional[Path] = None,
        audit_repo: Optional[AuditRepository] = None,
    ):
        self.db = db
        self.raw_dir = raw_storage_dir or Path("data/raw")
        self.source_repo = SourceRepository(db)
        self.audit_repo = audit_repo or AuditRepository(db)

    def prune_expired_data(
        self,
        default_retention_days: int = 90,
        dry_run: bool = False,
        operator_username: str = "system",
    ) -> RetentionPruneResult:
        """
        Execute retention pruning.
        - Identifies source-specific retention thresholds.
        - Prunes raw storage files older than retention policy.
        - Prunes completed/failed transient worker job records older than retention window.
        - CRITICAL RULE: Canonical articles, revisions, stories, and audit logs are 100% preserved.
        """
        now = datetime.now(timezone.utc)
        result = RetentionPruneResult(executed_at=now, dry_run=dry_run)

        # 1. Map retention windows per source_id
        sources = self.source_repo.list_sources()
        source_retention_map: dict[str, int] = {
            s.source_id: (s.policy.retention_days or default_retention_days) for s in sources
        }

        # 2. Prune transient raw files
        if self.raw_dir.exists():
            for root, _, files in os.walk(self.raw_dir):
                for fname in files:
                    file_path = Path(root) / fname
                    result.raw_files_evaluated += 1

                    try:
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                        # Determine source_id from parent folder if structured by source
                        rel_parts = file_path.relative_to(self.raw_dir).parts
                        src_id = rel_parts[0] if len(rel_parts) > 1 else None
                        retention_days = source_retention_map.get(
                            src_id or "", default_retention_days
                        )

                        cutoff = now - timedelta(days=retention_days)
                        if mtime < cutoff:
                            file_size = file_path.stat().st_size
                            result.bytes_reclaimed += file_size
                            result.raw_files_pruned += 1
                            if not dry_run:
                                file_path.unlink(missing_ok=True)
                    except Exception as exc:
                        logger.warning(
                            "Failed to inspect/prune raw file '%s': %s", file_path, exc
                        )

        # 3. Prune old completed/failed worker job records
        jobs_col = self.db["jobs"]
        jobs_cutoff = now - timedelta(days=default_retention_days)
        transient_query = {
            "status": {"$in": ["completed", "failed", "cancelled"]},
            "updated_at": {"$lt": jobs_cutoff},
        }
        transient_count = jobs_col.count_documents(transient_query)
        result.transient_jobs_pruned = transient_count
        if not dry_run and transient_count > 0:
            jobs_col.delete_many(transient_query)

        # 4. Count and verify canonical preservation
        result.canonical_articles_preserved = self.db["articles"].count_documents({})
        result.audit_logs_preserved = self.db["audit_logs"].count_documents({})

        result.diagnostics.append(
            f"{'[DRY RUN] Would prune' if dry_run else 'Pruned'} {result.raw_files_pruned} expired raw files ({round(result.bytes_reclaimed / (1024**2), 2)} MB) and {result.transient_jobs_pruned} old transient jobs."
        )
        result.diagnostics.append(
            f"Preserved {result.canonical_articles_preserved} canonical articles and {result.audit_logs_preserved} audit logs intact."
        )

        if not dry_run:
            self.audit_repo.record(
                actor_id=operator_username,
                action="retention_prune_executed",
                entity_type="system_storage",
                entity_id="raw_storage",
                details={
                    "raw_files_pruned": result.raw_files_pruned,
                    "bytes_reclaimed": result.bytes_reclaimed,
                    "transient_jobs_pruned": result.transient_jobs_pruned,
                },
            )

        return result
