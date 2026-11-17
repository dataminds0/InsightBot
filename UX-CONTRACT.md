# InsightBot — UX Contract & Interaction Specification

- **Version:** 2.0.0
- **Audience:** Frontend Engineers, QA Automation, UX Designers
- **Scope:** State Management, URL Synchronization, Screen Contracts, Error Boundaries

---

## 1. Authentication & Session Contract

| User Action | System State Transition | Expected UX Behavior |
|---|---|---|
| Valid Login | `Unauthenticated` -> `Authenticated` | Store session cookie (HttpOnly/SameSite), redirect to primary `/` feed, display user role pill in Header. |
| Role Change by Admin | Active session invalidated | Next request receives 401; user redirected to `/login` with notification: "انتهت صلاحية الجلسة؛ يرجى تسجيل الدخول مجدداً". |
| Background Poll | Idle timer preserved | Periodic notifications polling does NOT refresh analyst idle timer; session safely expires after 15m of user inactivity. |
| Logout | Session destroyed | Client cache purged, user redirected to `/login`. |

---

## 2. URL State Synchronization Contract

All primary filters and pagination states must synchronize bidirectionally with browser URL search parameters:

| URL Parameter | Type | Default | Description |
|---|---|---|---|
| `q` | `string` | `""` | Search query text for hybrid BM25 / vector retrieval. |
| `lang` | `enum(ar,en,ru)` | `all` | Publisher language filter chip. |
| `source` | `string` | `all` | Specific publisher source ID filter. |
| `story` | `string` | `""` | Active story ID opening comparative drawer. |
| `tab` | `enum(overview,perspectives,timeline,claims,briefing)` | `overview` | Selected tab within Event Comparison view. |
| `cursor` | `string` | `""` | Deterministic opaque pagination cursor. |

**Contract Rules:**
- Navigating with browser Back/Forward buttons must restore exact filter chips and selected tabs.
- Sharing a URL with colleagues must open the identical filtered view without requiring manual re-filtering.

---

## 3. Screen Contracts

### Screen 1: Primary Feed (`ArticleList.tsx`)
- **Memory Defense:** Listing queries strictly fetch lightweight projections (`{"body_text": 0}`). Full article body text is fetched only when the user clicks an individual article.
- **Reading Time:** Displays estimated reading time calculated from word count ($\text{wc} / 200$).
- **Publication Dates:** Displays publication timestamp. If date was missing from publisher, explicitly renders `[تاريخ غير محدد]` (Defect A13).

### Screen 2: Event Comparison (`EventComparisonView.tsx`)
- **Divergence Highlighting:** When numerical divergences exist (e.g., conflicting casualties or financial figures), displays an amber divergence badge with attribution to specific publishers.
- **Analyst Exclusion:** Analysts can exclude an erroneous or quarantined article from story synthesis with required justification notes.
- **Briefing Tab:** Renders generated summary accompanied by passage citations with verified quotes. If relevance is low, displays calibrated abstention notice.

### Screen 3: Analyst Workspace (`WorkspaceView.tsx`)
- **IDOR Protection:** Bookmarks, queries, and notes are strictly partitioned by authenticated user ID; cross-user manipulation returns 403 Forbidden.
- **Notification Dedup:** Historical reprocessing guarantees zero duplicate in-app alerts on replay.
- **Cooldown Selector:** Alert rules provide 1h, 6h, and 24h cooldown windows to prevent alert fatigue.

---

## 4. Error Boundaries & Honest States

1. **Empty States:** When a search returns zero results, the system offers clear query reformulation suggestions rather than a blank white screen.
2. **Network Disconnection:** Displays a subtle non-blocking banner ("تعذر الاتصال بالخادم، جارٍ إعادة المحاولة تلقائياً").
3. **Quarantined Articles:** If an article is flagged for quarantine, the detail view displays the quarantine reason and prevents it from appearing in story briefings.
