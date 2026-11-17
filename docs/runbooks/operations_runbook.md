# InsightBot — Operations & Second-Operator Runbook

- **Version:** 2.0.0
- **Audience:** DevOps Engineers, System Administrators, Security Officers
- **Mandate:** Comprehensive clean-environment deployment and incident handling without missing verbal instructions.

---

## 1. Clean Environment Bootstrap Walkthrough

Follow these sequential steps to deploy InsightBot from scratch on a clean host:

### Step 1: System Requirements & Hardware Verification
Run the automated hardware profiler to verify CPU, memory, and disk capacity:
```bash
uv run insightbot benchmark run --samples 10 --concurrency 2
```
*Gate Acceptance:* System must have $\ge 4$ CPU cores, $\ge 8$ GB RAM, and pass projection memory bounds ($\ge 80\%$ payload reduction).

### Step 2: Production Container Deployment
Launch core databases and orchestrator using Docker Compose:
```bash
docker compose -f infra/compose.prod.yaml up -d mongo prefect
```
Verify containers are healthy (`docker ps`).

### Step 3: Database Schema Migrations
Execute idempotent schema migrations to create collections and strict unique indexes:
```bash
uv run insightbot db migrate --apply
```
*Gate Acceptance:* Verified that unique index on `canonical_url` and composite indexes are created cleanly.

### Step 4: First Administrator Provisioning (No Seeds)
Interactively provision the primary administrator account (zero predefined passwords):
```bash
uv run insightbot admin create --username "lead_admin" --email "admin@organization.org"
```
*Note:* The password is encrypted using Argon2id. No fixed admin seeds exist in the repository.

### Step 5: Publisher Sources Validation & Baseline Ingestion
Validate publisher source definitions and synchronize them to MongoDB:
```bash
uv run insightbot sources validate --sync
```
*Note:* All sources are disabled by default (`enabled: false`). To activate approved baseline sources:
```bash
uv run insightbot sources batch list
uv run insightbot sources batch activate "batch_baseline_2026" --user "lead_admin"
```

### Step 6: Worker Execution & Ingestion Flow
Start the background ingestion and processing worker:
```bash
uv run insightbot ingest --source "aljazeera_ar" --limit 10
uv run python -m insightbot.flows.worker
```

### Step 7: Automated Security & Quality Audit
Execute the security audit suite to verify SSRF, CSV injection, prompt injection, and seed absence:
```bash
uv run insightbot security audit
```
*Gate Acceptance:* Must output `SECURITY GATES AUDIT VERDICT: PASS (Zero blocking defects)`.

### Step 8: Disaster Recovery Restore Drill
Run an automated backup and test restoration into an isolated drill target database:
```bash
uv run insightbot backup create
uv run insightbot backup restore-drill data/backups/<backup_id>
```
*Gate Acceptance:* Must report `RESTORE DRILL VERDICT: PASS` and RTO $< 10$ seconds.

### Step 9: Legacy Data Migration (Historical Import)
Audit and import historical news collections safely without URL collisions:
```bash
uv run insightbot db inventory --csv-path data/raw/data.csv
uv run insightbot db migrate-legacy --csv-path data/raw/data.csv --dry-run
uv run insightbot db migrate-legacy --csv-path data/raw/data.csv
```

---

## 2. Standard Operational Procedures

### Scheduled Automated Backups
Automated backups run via cron executing the bundled script:
```bash
bash infra/backup/backup.sh
```
Backups write timestamped JSONL archives, SHA-256 manifests, and raw storage snapshots to `data/backups/`.

### Storage Retention Pruning
Prune transient raw HTML snapshots and expired worker jobs older than source retention windows (90 days):
```bash
# Dry run report
uv run insightbot backup prune --days 90 --dry-run

# Actual pruning
uv run insightbot backup prune --days 90
```
*Preservation Guarantee:* Canonical articles, revisions, stories, and audit logs are 100% preserved.

---

## 3. Incident Response Playbooks

### Incident A: Publisher Rate Limiting (HTTP 429) / Scraper Regressions
1. **Symptom:** Worker logs display repeated 429 or blocked responses from a newly added source batch.
2. **Action:** Execute atomic batch rollback:
   ```bash
   uv run insightbot sources batch rollback "batch_name" --reason "Upstream 429 rate limiting" --user "oncall_engineer"
   ```
3. **Outcome:** All sources in that expansion batch are instantly disabled without affecting baseline collection.

### Incident B: Memory Pressure or Container OOM
1. **Symptom:** Worker container memory exceeds 1.8 GB.
2. **Action:** Verify listing endpoints use projection:
   ```bash
   uv run insightbot benchmark run
   ```
3. Ensure no custom query is returning `body_text` in listing queries (Defect A12).

### Incident C: Stale Worker Process / Lease Lock Contention
1. **Symptom:** A crashed worker left an active lease on a publisher source.
2. **Action:** MongoDB lease expires automatically after 60 seconds (`lease_expires_at`). The next worker iteration will atomically reclaim the job using monotonic fencing tokens (`fencing_token += 1`). No manual database surgery is required.
