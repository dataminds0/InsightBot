# InsightBot — Product Specification

## 1. Product Vision & Principles
InsightBot is a self-hosted, multilingual news intelligence and analysis platform designed for journalists, researchers, and intelligence analysts. It operates completely independently of external paid APIs, cloud subscriptions, or expiring AI credits.

### Core Principles
- **Real Provenance Only:** Zero synthetic seeds, mock articles, or hardcoded administrative credentials. Every document originates from real publisher feeds or crawl targets with full URL and timestamp provenance.
- **Full Text & Version Integrity:** Publisher bodies are never truncated or overwritten by summaries. Content changes create immutable version revisions with monotonically increasing fencing tokens.
- **Resource Discipline:** Article list endpoints use database-level projections that strictly exclude full body text (`{"body_text": 0}`), preventing whole-corpus memory exhaustion (Defect A12).
- **RTL-First Arabic Workspace:** First-class Arabic user experience with bidirectional language support (Arabic, English, Russian) adhering to WCAG 2.2 AA accessibility standards.

---

## 2. User Personas & Roles

| Role | Responsibilities & Capabilities |
| :--- | :--- |
| **Viewer** | Search, filter, and read collected news articles; view immutable version histories and provenance metadata; inspect source policies. |
| **Analyst** | All Viewer capabilities plus workspace bookmarks, private analytical notes, saved queries, and automated analytical briefings. |
| **Admin** | Full system administration; user approval, role elevation, and account disabling; source registry management and scraping worker orchestration; audit inspection. |
| **Worker** | Background daemon executing feed discovery, bounded HTML fetching, Trafilatura extraction, and index reconciliation. |

---

## 3. Core User Journey
1. **Authentication:** User logs in securely with Argon2id-verified credentials or registers a new account (held in pending status awaiting admin approval).
2. **News Exploration:** Filter live feeds across approved publishers (`aljazeera_ar`, `bbc_ar`, `reuters_en`, etc.), filter by language, publication date window, or search keywords.
3. **Deep Reader & Evidence:** Open an individual article to read the full extracted text in high-legibility Arabic typography with a dedicated Evidence Strip (source, original URL, published vs. fetched timestamp, content hash, and revision history).
4. **Version Comparison:** Inspect previous revisions of updated stories to track editorial changes and developing news.
5. **System Governance:** Administrators monitor source health, review worker logs, and manage analyst accounts.
