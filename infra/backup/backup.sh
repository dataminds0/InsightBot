#!/usr/bin/env bash
# ==============================================================================
# InsightBot Scheduled Backup Execution Shell Script
# Runs database, configuration, and raw storage backup with integrity verification
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo " Starting InsightBot Production Backup Job (Task T23)"
echo "=========================================================="

python infra/backup/backup.py

echo "Backup job completed successfully."
