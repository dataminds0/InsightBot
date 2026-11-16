# InsightBot — Design System & Visual Specification

## 1. Aesthetic Foundation
InsightBot follows a **Calm Intelligence** aesthetic: minimal visual clutter, high contrast, clean typography, and explicit visual separation between original news content and machine metadata.

---

## 2. Color Tokens

| Token | Hex | Role & Usage |
| :--- | :--- | :--- |
| `canvas` | `#F5F8FA` | Application background behind cards and containers. |
| `surface` | `#FFFFFF` | Primary card, modal, and panel background. |
| `text` | `#172C3C` | High-contrast primary reading text (WCAG AAA compliant on surface). |
| `muted` | `#506474` | Secondary labels, timestamps, metadata captions. |
| `brand` | `#0B6C70` | Primary actions, navigation active states, key interactive elements. |
| `brand-hover` | `#09575A` | Hover state for brand buttons. |
| `brand-light` | `#E6F4F5` | Background for active filter pills and selected items. |
| `border` | `#D2DCE3` | Structural dividers, card borders, form input outlines. |
| `positive` | `#24734D` | Active accounts, enabled sources, healthy worker status. |
| `negative` | `#AD3548` | Error banners, disabled status, critical alerts. |
| `warning` | `#8D5D0C` | Pending approval status, quarantine warnings, unknown dates. |
| `focus` | `#006FD6` | Visible keyboard focus outline ring (3px). |

---

## 3. Typography & RTL

- **Primary Font Family:** `"Noto Sans Arabic"`, system-ui, -apple-system, sans-serif.
- **Direction:** `dir="rtl"` by default on root HTML, with automatic LTR isolation for English/Russian titles and URLs.
- **Scale:**
  - Micro / Captions: `12px` (line-height 1.4)
  - Small / Metadata: `14px` (line-height 1.5)
  - Base / UI Elements: `16px` (line-height 1.5)
  - Long-form Reader: `18px` with `line-height: 1.8` for fatigue-free Arabic text reading.
  - Headings: `20px` (H3), `24px` (H2), `30px` (H1).

---

## 4. Evidence Strip Specification
Every article detail view includes a permanent Evidence Strip placed immediately below the headline:
1. **Source Publisher Badge:** Tag with source name and link to homepage.
2. **Original Link:** External outbound icon with `rel="noopener noreferrer"`.
3. **Publication Timestamp:** Displayed in local user time, clearly labelled "تاريخ النشر" (or "تاريخ النشر: غير محدد" if missing).
4. **Fetch Timestamp:** Labelled "تاريخ الجلب" to guarantee zero confusion between publication time and crawl time (Fixing Defect A13).
5. **Version & Hash:** Displayed as `v{current_version}` with SHA-256 fingerprint snippet.
