"""Standalone runner script for legacy data inventory and migration (Task T24)."""

import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).resolve().parents[2]
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from insightbot.config import get_settings  # noqa: E402
from insightbot.infra.mongo import get_mongo_client  # noqa: E402
from insightbot.modules.operations.migration import LegacyMigrationService  # noqa: E402


def main() -> None:
    csv_path = project_root / "data" / "raw" / "data.csv"
    if not csv_path.exists():
        csv_path = project_root / "data" / "report_data" / "data.csv"

    if not csv_path.exists():
        print(f"[ERROR] Legacy CSV not found at '{csv_path}'")
        sys.exit(1)

    settings = get_settings()
    from insightbot.infra.mongo import check_mongo_connection  # noqa: E402

    ok, msg = check_mongo_connection(settings)
    if not ok:
        print(
            f"[INFO] Live MongoDB not reachable ({msg}). Running migration dry-run in offline in-memory simulation mode..."
        )
        import mongomock

        client = mongomock.MongoClient()
        db = client[settings.mongo_db]
    else:
        client = get_mongo_client(settings)
        db = client[settings.mongo_db]

    service = LegacyMigrationService(db)

    print("=" * 80)
    print("           INSIGHTBOT LEGACY DATA MIGRATION RUNNER (T24)")
    print("=" * 80)

    # 1. Scan Inventory
    inventory = service.scan_inventory(csv_path)
    print(f"Dataset path: {inventory.csv_path}")
    print(f"Total rows: {inventory.total_rows}")
    print(f"Unique URLs: {inventory.unique_urls} (Duplicates: {inventory.duplicate_urls})")
    print(f"Sources distribution: {inventory.sources_distribution}")
    print(
        f"Dates: {inventory.valid_publication_dates} valid, {inventory.missing_publication_dates} unknown"
    )
    print(f"Average word count: {inventory.average_word_count}")

    # 2. Dry-run validation
    print("\nExecuting dry-run migration validation...")
    dry_report = service.migrate_legacy_csv(csv_path, dry_run=True)
    for diag in dry_report.diagnostics:
        print(f" * {diag}")

    # 3. Check seeded accounts
    suspects = service.review_seeded_accounts()
    print(f"\nAccount Review: Found {len(suspects)} flagged accounts requiring human review.")
    for s in suspects:
        print(f" - [{s['username']}] {s['email']} | {s['reasons']}")

    client.close()
    print("\n[SUCCESS] Legacy migration dry-run completed successfully.")


if __name__ == "__main__":
    main()
