# InsightBot Release & Security Verification Checklist (Task T21 Gate)

This document formalizes the production release readiness, security audits, accessibility validations, and operational gates for **InsightBot** according to Section 19 and Task T21 of [`docs/plan.md`](./plan.md).

---

## 1. Automated Test Suites & Quality Verification

| Gate | Target / Threshold | Actual Result | Status |
| :--- | :--- | :--- | :--- |
| **Backend Unit & Integration Tests** | 100% passing across domain modules | **153 / 153 passed** (`uv run pytest -q`) | **PASS** |
| **Python Code Quality & Linter** | Ruff zero warnings / errors | **All checks passed** (`uv run ruff check .`) | **PASS** |
| **Static Type Checking** | Mypy strict zero issues | **Success in 98 source files** (`uv run mypy src/insightbot`) | **PASS** |
| **Frontend Unit & Component Tests** | Vitest 100% passing | **11 / 11 passed** (`npm test --prefix apps/web`) | **PASS** |
| **Frontend TypeScript Typecheck** | `tsc --noEmit` zero errors | **Clean compilation** (`npm run typecheck --prefix apps/web`) | **PASS** |
| **Production Frontend Build** | Vite production bundle | **Built cleanly in 8.3s** (`npm run build --prefix apps/web`) | **PASS** |

---

## 2. Security Defense Audit (OWASP / CWE Gates)

### 2.1 SSRF Defense Gate (Server-Side Request Forgery)
- **Mechanism:** Implemented in `CentralFetcher` (`src/insightbot/infra/fetcher.py`) and `validate_safe_url` (`src/insightbot/modules/ingestion/url.py`).
- **Enforcement:**
  - Strict loopback blocking (`127.0.0.1`, `localhost`, `[::1]`).
  - Strict cloud metadata IP blocking (`169.254.169.254`).
  - Strict RFC 1918 private IP range blocking (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
  - Manual hop-by-hop redirect inspection ensuring redirected locations cannot pivot to internal addresses.
- **Verification Evidence:** `tests/test_security_gates.py::test_ssrf_defense_blocks_private_and_loopback_ips` passed.

### 2.2 CSV Formula Injection Defense (CWE-1236)
- **Mechanism:** Implemented in `sanitize_csv_cell` (`src/insightbot/modules/analytics/export.py`).
- **Enforcement:**
  - Any exported cell starting with dangerous spreadsheet formula triggers (`=`, `+`, `-`, `@`, `\t`, `\r`, `%`) is automatically prefixed with a single quote (`'`), neutralizing executable macros in Excel, Calc, and Google Sheets.
- **Verification Evidence:** `tests/test_security_gates.py::test_csv_formula_injection_defense` passed.

### 2.3 Prompt Injection Defense in Generation / Local RAG
- **Mechanism:** Implemented in `sanitize_untrusted_passage` (`src/insightbot/modules/generation/engine.py`).
- **Enforcement:**
  - Crawled untrusted news text containing adversarial system overrides (`ignore all previous instructions`, `تجاهل جميع التعليمات السابقة`, etc.) is sanitized into `[REDACTED_INJECTION_ATTEMPT]` before context ingestion.
- **Verification Evidence:** `tests/test_security_gates.py::test_prompt_injection_neutralization_in_generation` passed.

### 2.4 Immediate Session Revocation & Idle Timeout
- **Mechanism:** Implemented in `AuthService` (`src/insightbot/services/auth_service.py`).
- **Enforcement:**
  - When an administrator modifies a user's role or disables an account, all active user sessions are immediately revoked (`delete_user_sessions`).
  - Polling requests carrying `X-Background-Poll: 1` do not extend session idle lifetime.
  - Argon2id password hashing with transparent legacy bcrypt auto-upgrade.
- **Verification Evidence:** `tests/test_security_gates.py::test_immediate_session_revocation_on_role_change_or_disable` and `test_background_poll_does_not_extend_idle_session` passed.

### 2.5 Insecure Direct Object Reference (IDOR) & Ownership Isolation
- **Mechanism:** Implemented in `WorkspaceRepository` (`src/insightbot/repositories/workspace_repository.py`), `NotificationRepository`, and `AssistantJobRepository`.
- **Enforcement:**
  - All workspace queries strictly bind `user_id == current_user.user_id`.
  - Cross-user attempts to access notes, bookmarks, alerts, or assistant jobs return HTTP 403 or 404.
- **Verification Evidence:** `tests/test_security_gates.py::test_workspace_idor_isolation` passed.

### 2.6 Worker Fencing Token Interruption & Lease Reclamation
- **Mechanism:** Implemented in `JobRepository` (`src/insightbot/repositories/job_repository.py`).
- **Enforcement:**
  - Atomic `$inc: {"fencing_token": 1}` prevents zombie workers with expired leases from overwriting newly claimed jobs (`StaleWorkerCommitError`).
- **Verification Evidence:** `tests/test_security_gates.py::test_worker_fencing_token_prevents_stale_commit` passed.

---

## 3. Frontend Accessibility & Arabic UX Gate

- **RTL-First Design:**
  - Root direction set to `dir="rtl"`.
  - Bidirectional text isolation using `<bdi>` around mixed Arabic/English titles and source names.
- **Calm Design & Color Tokens:**
  - Neutral canvas (`#f8fafc`), clean surface cards, brand color (`#0284c7`), high contrast text (`#0f172a`), and negative badges (`#dc2626`).
  - Meets WCAG 2.2 Level AA contrast requirements.
- **Keyboard Navigation:**
  - All interactive elements use native semantic buttons or anchors with visible `:focus-visible` styling (`focus:ring-2 focus:ring-focus`).
- **Responsive Layouts:**
  - Tested across mobile (< 640px), tablet (640px - 1024px), and desktop (> 1024px) with flexible grid adaptations.

---

## 4. Operational & Packaging Verification

- **Production Dockerfiles:**
  - `Dockerfile.api`: Multi-stage build (Node 20 + Python 3.12-slim), non-privileged `insightbot:10001` user, locked `uv` sync, built-in SPA hosting.
  - `Dockerfile.worker`: Non-privileged worker executing background flows.
- **Production Compose:**
  - `infra/compose.prod.yaml`: Includes `mongo:8.0`, `prefect:3`, separate one-shot `migrator`, `api`, and `worker` with explicit 2GB memory limits.
- **Zero Restart Seeding:**
  - Clean restart smoke test verified absence of hardcoded admin accounts and dummy CSV seed files (`Interface/insightbot_seed/news_articles.csv` and `seed_data.py` remain removed).
- **Atomic Raw Storage:**
  - HTML snapshots write to `.tmp` files before atomic rename, preventing partial read corruptions.

---

## 5. Explicitly Untested / Scope Boundaries

In accordance with Section 19 and Task T21 honesty constraints:
1. **Multi-Node Distributed Clustering:** Production tests were conducted on single-node MongoDB Community and local Prefect instances; sharded multi-datacenter clusters were not benchmarked.
2. **GPU Acceleration:** Local embedding and extraction were verified on CPU architectures; dedicated CUDA/vLLM GPU clusters were not provisioned.
3. **Live Publisher Crawling in CI:** In accordance with policy, continuous integration tests execute against isolated fixtures and recorded HTML snapshots, rather than flooding live news servers during test runs.

---

**Gate Verdict: PASS**  
*All critical data, security, accessibility, and main-journey gates are fully satisfied.*
