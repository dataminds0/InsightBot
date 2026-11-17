"""Automated backup runner script for cron jobs and container orchestration (Task T23)."""

import sys
from pathlib import Path

# Ensure src is on Python path
project_root = Path(__file__).resolve().parents[2]
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from insightbot.config import get_settings  # noqa: E402
from insightbot.infra.mongo import get_mongo_client  # noqa: E402
from insightbot.modules.operations.backup import BackupService  # noqa: E402


def main() -> None:
    settings = get_settings()
    client = get_mongo_client(settings)
    db = client[settings.mongo_db]
    svc = BackupService(db)

    output_dir = project_root / "data" / "backups"
    backup_path, manifest = svc.create_backup(output_dir, include_raw=True)

    print(f"[SUCCESS] InsightBot Backup created: {manifest.backup_id}")
    print(f"Location: {backup_path}")
    print(f"Collections archived: {len(manifest.collections)}")
    print(f"Raw storage included: {manifest.has_raw_storage} ({manifest.raw_files_count} files)")

    valid, issues = BackupService.verify_backup(backup_path)
    if valid:
        print("[SUCCESS] Backup cryptographic checksums verified.")
    else:
        print(f"[ERROR] Integrity verification failed: {issues}")
        sys.exit(1)

    client.close()


if __name__ == "__main__":
    main()
