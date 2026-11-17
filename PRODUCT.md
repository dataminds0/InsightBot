# InsightBot — Product Specification & Domain Mandate

- **Version:** 2.0.0 (Production Release)
- **Status:** Complete & Verified (Tasks T01–T25)
- **Core Tenet:** 100% Self-Hosted Multilingual News Intelligence with Zero Paid API Dependencies

---

## 1. Product Vision

InsightBot is an enterprise-grade, self-hosted multilingual news intelligence platform engineered to collect, normalize, cluster, compare, and synthesize news coverage across Arabic, English, and Russian media ecosystems.

The platform provides editorial analysts and researchers with an objective, evidence-backed workspace that highlights multi-source perspectives, identifies numerical claim divergences, detects wire syndication, and performs local synthesis with verifiable exact-quote citations.

---

## 2. Target Personas

1. **Intelligence & News Analyst:**
   - Monitors real-time geopolitical and regional developments.
   - Cross-references multi-source reporting to detect conflicting figures, dates, and framing.
   - Generates executive briefings with strict evidence support and zero AI hallucinations.
2. **Editorial Lead / Research Supervisor:**
   - Manages publisher source registries and policy compliance.
   - Reviews story cluster merges, splits, and event coverage timelines.
   - Oversees source expansion batches and domain rate-limiting.
3. **Systems & Security Administrator:**
   - Operates air-gapped or self-hosted container deployments without external cloud subscriptions.
   - Executes disaster recovery restore drills, cryptographic backup audits, and retention pruning.
   - Enforces role-based access control (Viewer, Analyst, Admin) and session revocation.

---

## 3. Core Functional Capabilities

### A. Ingestion & Provenance Tracking (T04–T06)
- **Approved Publishers Registry:** Central registry with 8 baseline sources (Al Jazeera, BBC Arabic, Al Arabiya, Sky News Arabia, BBC World, Reuters, The Guardian, TASS), disabled by default until human editorial policy sign-off.
- **SSRF Defense:** Transport-level IP inspection on every HTTP redirect hop blocking loopback, link-local metadata (`169.254.169.254`), and RFC 1918 private subnets.
- **Raw Snapshot Archiving:** Preserves uncompressed original HTML in local disk storage (`data/raw/`) via atomic temporary writes, decoupling collection from extraction.
- **Trafilatura Extraction:** Preserves full-text structure, Arabic colon attribution, and exact punctuation without destructive normalization.
- **Fault-Tolerant Worker Leases:** Worker processes acquire atomic leases with monotonic fencing tokens in MongoDB (`jobs`), preventing split-brain or stale worker commits.

### B. NLP & Multilingual Processing (T12–T14)
- **Pinned Local Model Manifest:** Standardized models for embeddings (`multilingual-e5-small`), classification (`xlm-roberta-base`), and NER (`bert-base-multilingual-cased`).
- **Syndication & Deduplication:** Near-duplicate and wire copy detection using MinHash LSH and cosine embeddings without merging distinct publisher rows. Detects numerical discrepancies (e.g., 12 vs 45 casualties) to prevent false-duplicate merging.
- **Story Clustering & Lifecycle:** Aggregates coverage into dynamic story clusters progressing through defined lifecycle phases (`Emerging -> Peak -> Declining -> Closed`). Strict guards block cross-location conflict and enforce a 72-hour temporal cutoff.

### C. Search & Comparative Analysis (T15–T17)
- **Hybrid Search Engine:** Combines BM25 lexical ranking and 384-dimensional dense vector search using Reciprocal Rank Fusion ($k=60$) with zero-downtime alias swaps and dynamic safe snippet generation.
- **Multi-Source Event Comparison:** Side-by-side coverage matrix, unified chronological event timeline, and numerical claim divergence extraction.
- **Analytics & Secure Exports:** Trend aggregation, source publishing lag analysis, and multi-format exports (CSV, JSONL, Markdown) protected against CWE-1236 CSV Formula Injection with audit manifests.

### D. Evidence-Backed Local Generation & Assistant (T18–T19)
- **100% Self-Hosted Generation:** Local synthesis with strict passage budgets ($\le 6$ passages, $\le 256$ tokens/passage), prompt injection neutralization, and calibrated abstention when evidence is insufficient or relevance $< 0.15$.
- **Exact-Quote Citations:** Every generated sentence links directly to an active source article quotation with verified availability.
- **Analyst Assistant & Alerts:** In-app notification engine with replay idempotency ($0$ duplicate alerts on re-evaluation) and bounded analyst assistant.

### E. Packaging, Operations & Disaster Recovery (T20–T24)
- **Production Container Packaging:** Multi-stage `Dockerfile.api` and `Dockerfile.worker` running under unprivileged user (`insightbot:10001`) with explicit 2GB RAM resource limits.
- **Disaster Recovery:** Consistent JSONL backups with SHA-256 cryptographic verification, separate-target restore drill (< 2s recovery time, strictly $< 4\text{h}$ RTO), and source-specific retention pruning.
- **Legacy Migration:** Audited migration of 497 historical records with deterministic stable IDs, legacy numeric ID retention, and Defect A13 unknown date protection.

---

## 4. Defect Mitigation Matrix (Defects A01–A20)

| Defect ID | Description | Architectural Solution | Verified Task |
|---|---|---|---|
| **A01** | Hardcoded Admin Seed Credentials | Interactive CLI admin creation (`insightbot admin create`), Argon2id hashing, legacy seed files deleted | T03, T21 |
| **A02** | Synthetic Demo Article Import | Removed all seed files; collection uses real publisher URLs and timestamps | T01, T21 |
| **A03** | Paid External API Lock-in | 100% self-hosted modular monolith (HTTPX, Trafilatura, local models) | T01, T18 |
| **A04** | SSRF Vulnerability in Scraping | Transport-level IP inspection on every redirect hop in `validate_safe_url` | T04, T21 |
| **A05** | Destructive Text Cleaning | Trafilatura extraction preserving exact punctuation, quotes, and whitespace | T05 |
| **A06** | Loss of Arabic Colon Attribution | Title parser preserving Arabic colons (`:`, `：`) as speaker attribution | T05, T12 |
| **A07** | Stale Worker Commits / Split-Brain | Monotonic fencing tokens and atomic heartbeat leases in `JobRepository` | T06, T21 |
| **A08** | Unstable Numeric Article IDs | Deterministic SHA-256 stable IDs derived from normalized canonical URLs | T02, T24 |
| **A09** | Weak Index Collisions | Strict unique index on `canonical_url` halting on collision (`IndexCollisionError`) | T02, T24 |
| **A10** | Missing Role-Based Authorization | Granular RBAC (`Viewer`, `Analyst`, `Admin`) with immediate session revocation | T03, T21 |
| **A11** | Cross-User IDOR Vulnerability | Strict owner-scoped query boundaries on bookmarks, queries, and notes | T11, T21 |
| **A12** | Memory Exhaustion (OOM) on Listing | Strict MongoDB projection `{"body_text": 0}` saving 99.56% memory | T07, T22 |
| **A13** | Fabricated Publication Dates | Missing dates stored as `None` with explicit `publication_date_unknown_reason` | T09, T24 |
| **A14** | Missing Reading Time Indicator | Deterministic reading time calculated from word count ($\text{wc} / 200$) | T09 |
| **A15** | Untrusted HTML XSS Injection | Strict React JSX text escaping and DOMPurify sanitization in web views | T08, T21 |
| **A16** | CSV Formula Injection (CWE-1236) | Automated cell sanitization prepending `'` to `=`, `+`, `-`, `@`, `\t`, `%` | T17, T21 |
| **A17** | Hallucinated AI Generation | Passage-budgeted local synthesis with calibrated abstention and citation verification | T18 |
| **A18** | Duplicate Alert Spam on Replay | Compound unique index `(user_id, query_id, target_id)` ensuring replay idempotency | T19 |
| **A19** | Root Container Execution | Non-privileged system user (`insightbot:10001`) with explicit 2GB limits | T20 |
| **A20** | Untested / Fragile Dependencies | Pinned `uv.lock`, frozen builds, and 167 automated regression tests | T01, T21 |
