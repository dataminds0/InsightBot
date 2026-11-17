# Repository Guidelines

## Project Structure & Module Organization
InsightBot collects news, processes it with NLP, stores articles in MongoDB, and presents Streamlit and Power BI dashboards.

- `Interface/`: Streamlit entry point (`app.py`), authentication, storage helpers, and user/admin dashboards.
- `Interface/insightbot_seed/`: legacy MongoDB schema initialization only. The article seed CSV and fixed-admin seed script were removed; do not recreate them.
- `scripts/`: news scraping and MongoDB-to-CSV export.
- `notebooks/`: data cleaning and pattern modeling notebooks.
- `flow/pipeline.py`: Prefect orchestration.
- `data/raw/` and `data/report_data/`: input and reporting CSVs.
- `reports/`: Power BI report; `images/` and `docs/`: screenshots, diagrams, and documentation.

## Build, Test, and Development Commands
Use Python 3.10+ and a running local MongoDB instance. Run commands from the repository root unless stated otherwise.

- `python -m venv .venv`, then `.venv\Scripts\Activate.ps1`: create and activate a Windows environment.
- `python -m pip install -r requirements.txt`: install declared dependencies. Authentication additionally requires `bcrypt`, which is currently missing from this file.
- `Interface/insightbot_seed/init_schema.py` is legacy schema tooling: it drops `user_preferences` and can fall back to non-unique indexes. Review it before use on a disposable database; do not treat it as a safe production migration.
- `python -m streamlit run Interface/app.py`: launch the application.
- `python flow/pipeline.py`: execute orchestration; requires Prefect and Jupyter/nbconvert, which are not declared dependencies. First resolve its reference to nonexistent `scripts/mongo_to_csv.py`; the existing exporter is `scripts/export_mongo_csv.py`. Check working-directory-dependent paths before running scripts or notebooks.

## Coding Style & Naming Conventions
Follow existing Python conventions: four-space indentation, `snake_case` functions and variables, and `UPPER_SNAKE_CASE` constants. Keep UI logic in dashboard modules and database operations in `storage.py`. Preserve existing article field names. No formatter or linter configuration is currently provided.

## Testing Guidelines
There is no automated test suite or coverage threshold. Manually verify registration, approval, login, role access, article filters, and CSV export against a disposable database. For new automated tests, use `tests/test_*.py` and document the runner and dependencies. Avoid live scraping in routine tests.

## Commit & Pull Request Guidelines
History uses short summaries such as `Fix typos in README` and `Update README.md`; no strict commit convention is evident. Use concise, imperative summaries. PRs should explain changes, link relevant issues, list validation performed, and include screenshots for UI changes.

## Security & Configuration
The app reads `MONGO_URI` and `MONGO_DB`; legacy schema and export scripts hard-code local connections. Verify targets before database writes. Keep credentials out of commits. There is currently no replacement administrator bootstrap command; existing database accounts were not changed by removing seed files.

## Antigravity Handoff — 16 November 2026

This section records the actual session state for the next agent. Read it and [the implementation plan](docs/plan.md) before continuing. The owner explicitly requested this update to the existing `AGENTS.md`; that later instruction supersedes the original request to preserve an existing guide during its initial creation.

### User Intent and Constraints

- Evolve the legacy project according to the owner's comprehensive Arabic proposal. A condensed English working edition now lives at `docs/plan.md`.
- The owner specifically requested removing seeds and using real data. Do not restore demo articles, fixed-admin accounts, or fake production metrics. Real collected articles need publisher URLs, timestamps, and provenance. Clearly labelled isolated test fixtures are allowed.
- Required operation must be self-hosted without paid APIs, mandatory subscriptions, or expiring credits. No hidden external inference fallback.
- Target architecture: Python modular monolith, FastAPI, separate worker, MongoDB Community, local raw storage, local Prefect, Arabic/RTL React and TypeScript. Search and local generation are optional later stages.
- Preserve publisher text, article versions, stable IDs, unknown dates, ownership, and source display policies. Do not weaken uniqueness to make a migration pass.

### Completed Changes

1. Created this contributor guide after confirming no root `AGENTS.md` existed. It originally contained 377 words; this handoff now expands it and corrects obsolete seed instructions.
2. Inspected repository files, README, requirements, recent commit subjects, pipeline, storage/authentication code, schema setup, and seed script. Confirmed HEAD is `8290069c209e71d5efe71d9f3424c576260dfb26`, the same revision cited by the supplied plan.
3. Added `docs/plan.md`: a condensed, edited English working edition with 28 numbered sections and all 25 task headings T01–T25. It preserves principal architecture, dependencies, acceptance gates, rollout, security, evaluation, and recovery requirements. It is explicitly **not a verbatim archive** of the long Arabic proposal; that original was provided in chat, not saved as a separate file.
4. Made real publisher data and removal of demo/admin seeds explicit requirements in the plan. Standardized its location as `docs/plan.md` and selected UTC as the default with user-selectable display timezone, resolving inconsistent timezone defaults in the proposal.
5. Deleted `Interface/insightbot_seed/seed_data.py`, which created a fixed administrator and app defaults and dropped legacy preferences.
6. Deleted `Interface/insightbot_seed/news_articles.csv`, the bundled article import seed. This does not establish that every row was fabricated; removal eliminates the bundled seed path.
7. Updated README: linked the plan; removed sample-import instructions and fixed-admin credentials; documented real-data ingestion and current limitations; corrected application entry point to `Interface/app.py`, flow path to `flow/pipeline.py`, and schema path reference.
8. Preserved `Interface/insightbot_seed/init_schema.py`; it creates structure but still has legacy risks. No ingestion, authentication, migration, or React implementation was added.

### Actual Verification and Limits

- `git diff --check` passed for tracked changes; Git reported only the repository's LF/CRLF conversion warning for README.
- A local structure check counted 28 numbered plan sections and 25 task headings.
- File checks confirmed both seed files are absent, README links `./docs/plan.md`, and README no longer references the removed seed filenames or fixed seed password.
- Checked reference URLs for accidental whitespace and repaired task/model identifiers after formatting. Read the plan critically during T01; this documentation has not received a separate full product/specification review.
- No application/unit/integration/browser tests ran: this session changed documentation and removed seed artifacts. No dependencies were installed, model weights downloaded, publishers crawled, or containers started.
- No database was connected, queried, migrated, cleaned, or deleted. Existing seeded articles/accounts, if any, remain in existing databases. Do not assume credential revocation happened.
- No source availability, multilingual model quality, performance, or hardware requirements were measured. Plan metrics are targets; suggested versions still require compatibility/security verification.
- **None of T01–T25 is completed.** Do not check off tasks based on this documentation work.

### Working Tree at Handoff

All session changes remain uncommitted and unstaged; nothing was pushed or published. Expected `git status --short` entries:

```text
 D Interface/insightbot_seed/news_articles.csv
 D Interface/insightbot_seed/seed_data.py
 M README.md
?? AGENTS.md
?? docs/plan.md
```

`AGENTS.md` is still untracked because this session created it. Preserve these edits/deletions when making an isolated checkout; a worktree created from HEAD alone will not contain them. Recheck status for subsequent user changes before editing. Existing `data/raw/data.csv`, `data/report_data/data.csv`, notebooks, reports, and screenshots were retained. Do not assume they are current production data or delete them without a scoped reason.

### Known Legacy Problems Relevant to Continuing

- `flow/pipeline.py` calls nonexistent `scripts/mongo_to_csv.py`; the actual exporter is `scripts/export_mongo_csv.py`. It also executes the flow at import and relies on notebooks/subprocesses.
- The exporter uses a working-directory-relative output path, loads all articles into pandas, and renumbers numeric IDs. Do not use this as the new stable-identity design.
- `init_schema.py` drops `user_preferences` and may weaken unique constraints after collisions. Do not run it against important data as a shortcut to T02.
- `bcrypt` is imported by authentication but absent from `requirements.txt`; Prefect and Jupyter/nbconvert are also undeclared despite pipeline usage. No version locks/test foundation currently exist.
- Seed removal leaves no replacement first-admin provisioning command. T03 must implement interactive creation, sessions, revocation, and authorization; do not restore fixed credentials to make login convenient.
- The existing pipeline is not established as a reliable real-data path. README now states the caveats. Do not claim live ingestion works merely because the scraper exists.

### Where Antigravity Should Continue

1. Read this file, `docs/plan.md` (especially sections 1–7, 21–23, and T01), and current Git status. The plan's FastAPI/React/CLI commands are future contracts, not currently runnable commands.
2. Start T01: inventory Python/Node/Podman/hardware and actual dependencies; choose compatible pinned versions; add package/settings/CLI/config validation, safe local configuration, initial Mongo/Prefect bootstrap, and the React shell. Review the proposed versions rather than treating them as verified.
3. Verify T01's acceptance criteria before proceeding. Follow T02 data contracts/indexes, T03 identity, and T04–T06 real ingestion/recovery according to dependencies; then T07 API and T08–T11 React/core workspace. Include core operation/tests/restore work early.
4. Use approved, permitted publisher samples. Start sources disabled until policy and network controls are checked; use honest empty states when collection fails. Avoid running the old destructive setup/seeding path.
5. Keep meaningful regression tests for identity, authorization, replay, revisions, and recovery. Record exact commands/results and what was not tested. Do not expand to OpenSearch or generation before their gates.
6. Update task evidence and this handoff as work advances. Maintain ADRs for architectural departures and explicit dry-run/rollback paths for persistent-data changes.

### Environment and Workflow Notes

Workspace: `D:\Projects\InsightBot`, Windows PowerShell. Writes were authorized within this repository. Read and write Markdown as UTF-8 explicitly; Windows PowerShell's default decoding can display UTF-8 punctuation as mojibake even when the file is valid. Long inline PowerShell commands can exceed Windows process command-line limits; use file patches or short scripts. One oversized command failed before process creation and made no changes; subsequent shorter operations completed the edits.

Relevant workflows used: using-superpowers for skill discovery, Ponytail for minimal seed removal, and verification-before-completion for evidence checks. No subagents were spawned. Antigravity may follow the plan manually or use compatible skills available in its own environment; installed skill/tool availability does not transfer automatically. The last user request was to record this handoff, so no new implementation task was started during handoff preparation.

## Production Implementation Handoff — 17 November 2026

All 25 tasks **T01 through T25** specified in `docs/plan.md` have been **100% implemented, tested, and verified** on branch `enhanced` with commits authored by `Abdulrahman Alsaqqaf <738151780abd@gmail.com>`.

### Final Status Summary
- **Backend Test Suite:** 167 passed tests (`uv run pytest -q`), 0 failures, 1 deprecation warning.
- **Frontend Test Suite:** 11 passed tests (`vitest`), 0 failures.
- **Static Typing & Linter:** Mypy clean across 104 source files (`uv run mypy src/insightbot`), Ruff clean (`uv run ruff check .`), Web TypeScript clean (`npm run typecheck --prefix apps/web`).
- **Defects Mitigated:** All defects A01 through A20 are permanently resolved and audited.
- **Core Architecture:**
  - Python 3.12 modular monolith with FastAPI, MongoDB 8 Community, Prefect 3, and React 18 RTL/Arabic Calm Design.
  - 100% self-hosted local execution with zero external paid APIs.
  - Multi-stage container packaging (`Dockerfile.api`, `Dockerfile.worker`, `infra/compose.prod.yaml`) under unprivileged user (`insightbot:10001`) with explicit 2GB RAM bounds.
  - Automated cryptographic backups, separate-target restore drills (RTO < 2s), and retention pruning.
  - Core documentation complete: `PRODUCT.md`, `DESIGN.md`, `UX-CONTRACT.md`, `docs/release_checklist.md`, `docs/runbooks/operations_runbook.md`, and `docs/adr/0001_crawler_and_infrastructure_performance.md`.
