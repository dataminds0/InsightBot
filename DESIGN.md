# InsightBot — Design System & Visual Specification

- **Version:** 2.0.0
- **Philosophy:** Calm Design (تصميم هادئ) — High Information Density, Low Cognitive Fatigue
- **Primary Direction:** Right-to-Left (RTL Arabic-first) with full LTR Bi-Directional Support
- **Source Token File:** `apps/web/src/styles/tokens.css`

---

## 1. Design Philosophy

InsightBot is designed for intelligence analysts and editorial researchers who process hundreds of complex multilingual news reports daily under strict deadlines.

Traditional news dashboards overwhelm users with aggressive red badges, animated tickers, and loud alerts. InsightBot adheres to **Calm Design**:
1. **Muted Neutral Palettes:** High-contrast, slate-based surfaces that eliminate eye strain during long analytical sessions.
2. **Predictable Visual Hierarchies:** Clear typographical weights, consistent 4px/8px spatial rhythm, and structured content cards.
3. **Information Density with Breathing Room:** Compact data representations that allow viewing multi-source timelines without horizontal scrolling.
4. **Honest States:** Distinct indicators for unknown dates, unverified summaries, and quarantined content.

---

## 2. Typography & Fonts

### Font Families
- **Primary Arabic Font:** `IBM Plex Sans Arabic`, `Noto Sans Arabic`, sans-serif.
- **Primary Latin Font:** `Inter`, system-ui, sans-serif.
- **Monospace Code/Data Font:** `JetBrains Mono`, `Fira Code`, monospace.

### Type Scale
- **Display 1 (Hero/Header):** 28px (1.75rem), SemiBold (600), Line Height: 1.3
- **Heading 1 (Screen Title):** 22px (1.375rem), SemiBold (600), Line Height: 1.35
- **Heading 2 (Card Title / Section):** 18px (1.125rem), Medium (500), Line Height: 1.4
- **Body Regular (Article Content):** 15px (0.9375rem), Regular (400), Line Height: 1.6
- **Body Small (Metadata, Timestamps):** 13px (0.8125rem), Regular (400), Line Height: 1.5
- **Caption / Badge:** 11px (0.6875rem), Medium (500), Line Height: 1.4

---

## 3. Color Tokens

### Surface Hierarchy
- `--bg-primary`: `#0f172a` (Slate 900 — deep canvas background)
- `--bg-surface`: `#1e293b` (Slate 800 — primary card and container surface)
- `--bg-surface-elevated`: `#334155` (Slate 700 — popovers, modals, dropdowns)
- `--bg-surface-subtle`: `#131d31` (Secondary container backgrounds)

### Borders & Dividers
- `--border-subtle`: `rgba(148, 163, 184, 0.12)`
- `--border-default`: `rgba(148, 163, 184, 0.24)`
- `--border-focus`: `#38bdf8` (Sky 400 — high-visibility focus ring)

### Text Contrast
- `--text-primary`: `#f8fafc` (Slate 50 — highest contrast reading text)
- `--text-secondary`: `#94a3b8` (Slate 400 — metadata, timestamps, word counts)
- `--text-muted`: `#64748b` (Slate 500 — inactive labels, placeholder text)

### Semantic Lifecycle Status Colors
- **Emerging Story:** Amber (`#f59e0b` / `rgba(245, 158, 11, 0.15)`)
- **Peak Story:** Emerald (`#10b981` / `rgba(16, 185, 129, 0.15)`)
- **Declining Story:** Sky Blue (`#0ea5e9` / `rgba(14, 165, 233, 0.15)`)
- **Closed Story:** Slate (`#64748b` / `rgba(100, 116, 139, 0.15)`)

---

## 4. Key Component Patterns

### A. Article Cards (`ArticleCard.tsx`)
- Displays publisher badge with language indicator (`ar`, `en`, `ru`).
- Dual timestamp display: Publication date (with explicit `[تاريخ غير محدد]` when unknown, Defect A13) and crawl timestamp.
- Reading time calculation badge (Defect A14).
- Bookmark toggle with immediate optimistic visual feedback and IDOR ownership protection.

### B. Story Detail & Multi-Source Comparison (`EventComparisonView.tsx`)
- **Tab 1: Overview:** Story lifecycle badge, total sources, article count, and lead summary.
- **Tab 2: Side-by-Side Perspectives:** Publisher reporting columns comparing perspective, framing, and attribution.
- **Tab 3: Chronological Timeline:** Unified chronological feed sorting events across all reporting sources.
- **Tab 4: Numerical Claims:** Highlighted divergence badges comparing casualty counts, monetary damages, or participant numbers.
- **Tab 5: Evidence-backed Briefing:** Local synthesis output featuring exact-quote citations and calibrated abstention banners.

### C. Workspace & In-App Alerts (`WorkspaceView.tsx`)
- Analyst personal collection: Bookmarks, Saved Searches, and Notes.
- Alert rules configuration: Query binding, cooldown period selector (1h, 6h, 24h), and active/paused state toggles.

---

## 5. Accessibility & Responsive Breakpoints

- **Mobile (< 768px):** Single-column layout, bottom navigation drawer, touch-friendly tap targets ($\ge 44\times 44\text{px}$).
- **Tablet (768px – 1024px):** Collapsible sidebar, 2-column article grid.
- **Desktop (1024px – 1440px):** Full navigation sidebar, 3-column feed, split-screen article reader modal.
- **Ultra-Wide (> 1440px):** Multi-pane comparative analytics view with fixed max-width readability container (max 1600px).
- **Keyboard Navigation:** Full Tab navigation order, high-contrast focus rings, Escape key modal dismiss.
