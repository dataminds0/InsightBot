"""Legacy dataset inventory, transformation, and migration service (Task T24)."""

import csv
import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from pymongo.database import Database

from insightbot.models.article import Article, ArticleRevision, compute_content_hash
from insightbot.modules.ingestion.url import normalize_canonical_url
from insightbot.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


class LegacyInventorySummary(BaseModel):
    """Statistical summary of legacy data inventory before migration."""

    csv_path: str
    total_rows: int
    unique_urls: int
    duplicate_urls: int
    sources_distribution: dict[str, int] = Field(default_factory=dict)
    valid_publication_dates: int
    missing_publication_dates: int
    min_word_count: int
    max_word_count: int
    average_word_count: float


class LegacyMigrationReport(BaseModel):
    """Detailed audit report of legacy data migration execution."""

    inventory: LegacyInventorySummary
    dry_run: bool
    migrated_articles_count: int = 0
    migrated_revisions_count: int = 0
    collisions_skipped: int = 0
    unknown_dates_handled: int = 0
    execution_duration_sec: float = 0.0
    passed_gate: bool = True
    diagnostics: list[str] = Field(default_factory=list)


def parse_iso_datetime(val: Optional[str]) -> Optional[datetime]:
    """Parse ISO formatted datetime string safely into timezone-aware UTC datetime."""
    if not val or not val.strip():
        return None
    cleaned = val.strip()
    # Normalize trailing Z to +00:00 for fromisoformat compatibility
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


class LegacyMigrationService:
    """
    Manages historical legacy CSV import, data inventorying, field normalization,
    and safe cutover according to Section 23 of docs/plan.md.
    """

    def __init__(self, db: Database[dict[str, Any]], audit_repo: Optional[AuditRepository] = None):
        self.db = db
        self.audit_repo = audit_repo or AuditRepository(db)

    def scan_inventory(self, csv_path: Path) -> LegacyInventorySummary:
        """Scan and audit legacy CSV file without writing to database."""
        if not csv_path.exists():
            raise FileNotFoundError(f"Legacy CSV file not found at: '{csv_path}'")

        total = 0
        seen_urls: set[str] = set()
        duplicate_urls = 0
        sources_dist: dict[str, int] = {}
        valid_pub_dates = 0
        missing_pub_dates = 0
        word_counts: list[int] = []

        with csv_path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                url = (row.get("url") or "").strip()
                if url in seen_urls:
                    duplicate_urls += 1
                else:
                    seen_urls.add(url)

                src = (row.get("source") or "unknown").strip()
                sources_dist[src] = sources_dist.get(src, 0) + 1

                pub_str = row.get("published_at")
                if pub_str and parse_iso_datetime(pub_str):
                    valid_pub_dates += 1
                else:
                    missing_pub_dates += 1

                content = (row.get("content") or "").strip()
                wc = len(content.split())
                word_counts.append(wc)

        min_wc = min(word_counts) if word_counts else 0
        max_wc = max(word_counts) if word_counts else 0
        avg_wc = round(sum(word_counts) / len(word_counts), 1) if word_counts else 0.0

        return LegacyInventorySummary(
            csv_path=str(csv_path),
            total_rows=total,
            unique_urls=len(seen_urls),
            duplicate_urls=duplicate_urls,
            sources_distribution=sources_dist,
            valid_publication_dates=valid_pub_dates,
            missing_publication_dates=missing_pub_dates,
            min_word_count=min_wc,
            max_word_count=max_wc,
            average_word_count=avg_wc,
        )

    def migrate_legacy_csv(
        self,
        csv_path: Path,
        dry_run: bool = False,
        operator_username: str = "analyst",
    ) -> LegacyMigrationReport:
        """
        Execute migration of legacy articles from CSV into canonical MongoDB collections.
        - Guarantees deterministic SHA-256 stable article_ids derived from canonical URLs.
        - Preserves legacy numeric IDs in extra_metadata["legacy_id"].
        - Marks missing published_at dates with Defect A13 unknown provenance.
        - Labels legacy summaries with legacy_summary_only.
        - Sets first_seen_at with basis=imported (Section 23).
        - Skips or reports collisions without corrupting active live-crawled articles.
        """
        t0 = time.perf_counter()
        inventory = self.scan_inventory(csv_path)

        articles_col = self.db["articles"]
        revisions_col = self.db["article_revisions"]

        migrated_articles = 0
        migrated_revisions = 0
        collisions_skipped = 0
        unknown_dates = 0
        diagnostics: list[str] = []

        now_utc = datetime.now(timezone.utc)
        seen_in_batch: set[str] = set()

        with csv_path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw_url = (row.get("url") or "").strip()
                if not raw_url:
                    continue

                canonical_url = normalize_canonical_url(raw_url)
                # Deterministic stable 24-character hex ID derived from canonical URL
                stable_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:24]

                # Check intra-batch duplicate or if already present in database
                if stable_id in seen_in_batch:
                    collisions_skipped += 1
                    continue
                seen_in_batch.add(stable_id)

                existing = articles_col.find_one({"article_id": stable_id})
                if existing:
                    collisions_skipped += 1
                    continue

                title = (row.get("title") or row.get("h1") or "بدون عنوان").strip()
                content = (row.get("content") or "").strip()
                source_val = (row.get("source") or "legacy_source").strip()

                # Defect A13: Handling publication dates safely
                pub_dt = parse_iso_datetime(row.get("published_at"))
                pub_unknown_reason = None
                if pub_dt is None:
                    pub_unknown_reason = "legacy_unspecified_date"
                    unknown_dates += 1

                fetch_dt = parse_iso_datetime(row.get("fetched_at")) or now_utc
                content_hash = compute_content_hash(content or title)

                extra_meta = {
                    "legacy_id": row.get("id"),
                    "legacy_source": source_val,
                    "first_seen_basis": "imported",
                    "legacy_summary_only": len(content.split()) < 30,
                    "migration_batch": "legacy_csv_cutover",
                }

                article = Article(
                    article_id=stable_id,
                    source_id=f"legacy_{source_val}",
                    canonical_url=canonical_url,
                    original_url=raw_url,
                    resolved_url=canonical_url,
                    title=title,
                    body_text=content,
                    content_hash=content_hash,
                    language=row.get("language") or "ar" if any(ord(c) > 0x0600 and ord(c) < 0x06FF for c in title) else "en",
                    published_at=pub_dt,
                    publication_date_unknown_reason=pub_unknown_reason,
                    fetched_at=fetch_dt,
                    first_seen_at=fetch_dt,
                    current_version=1,
                    word_count=len(content.split()),
                    extra_metadata=extra_meta,
                )

                revision = ArticleRevision(
                    article_id=stable_id,
                    version=1,
                    title=title,
                    body_text=content,
                    content_hash=content_hash,
                    operation="legacy_migration",
                    created_at=fetch_dt,
                )

                if not dry_run:
                    articles_col.insert_one(article.model_dump())
                    revisions_col.insert_one(revision.model_dump())

                migrated_articles += 1
                migrated_revisions += 1

        duration = round(time.perf_counter() - t0, 3)

        mode_str = "[DRY RUN] Simulated" if dry_run else "Executed"
        diagnostics.append(
            f"{mode_str} migration of {migrated_articles} articles and {migrated_revisions} revisions in {duration}s."
        )
        if collisions_skipped > 0:
            diagnostics.append(
                f"Skipped {collisions_skipped} existing URL collisions to protect canonical articles."
            )
        diagnostics.append(
            f"Handled {unknown_dates} records with missing publication dates with explicit unknown provenance."
        )

        if not dry_run:
            self.audit_repo.record(
                actor_id=operator_username,
                action="legacy_csv_migration",
                entity_type="dataset",
                entity_id=str(csv_path.name),
                details={
                    "articles_migrated": migrated_articles,
                    "collisions_skipped": collisions_skipped,
                    "unknown_dates_handled": unknown_dates,
                    "duration_seconds": duration,
                },
            )

        return LegacyMigrationReport(
            inventory=inventory,
            dry_run=dry_run,
            migrated_articles_count=migrated_articles,
            migrated_revisions_count=migrated_revisions,
            collisions_skipped=collisions_skipped,
            unknown_dates_handled=unknown_dates,
            execution_duration_sec=duration,
            passed_gate=True,
            diagnostics=diagnostics,
        )

    def review_seeded_accounts(self) -> list[dict[str, Any]]:
        """
        Explicit review of legacy/seeded accounts (Section 23).
        Never performs blanket automatic deletion; returns flagged accounts with review advice.
        """
        users_col = self.db["users"]
        suspects: list[dict[str, Any]] = []

        for user_doc in users_col.find({}):
            username = user_doc.get("username", "")
            email = user_doc.get("email", "")
            pw_hash = user_doc.get("password_hash", "")

            is_suspect = False
            reasons = []

            if username in ["admin", "demo", "seed", "test"]:
                is_suspect = True
                reasons.append(f"Generic administrative name '{username}'")

            if email.endswith("@example.com") or "seed" in email or "test" in email:
                is_suspect = True
                reasons.append(f"Synthetic demo email domain '{email}'")

            if pw_hash.startswith("$2b$") or pw_hash.startswith("$2a$"):
                reasons.append("Legacy bcrypt password hash (pending Argon2id upgrade)")

            if is_suspect:
                suspects.append(
                    {
                        "user_id": user_doc.get("user_id"),
                        "username": username,
                        "email": email,
                        "role": user_doc.get("role"),
                        "is_active": user_doc.get("is_active", True),
                        "reasons": reasons,
                        "recommended_action": "Manual analyst verification; disable if unused, rehash on login",
                    }
                )

        return suspects
