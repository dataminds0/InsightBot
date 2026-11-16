# InsightBot — UX Screen States Contract

## 1. Required Application Screen States

Every data-driven view in InsightBot must implement the following 8 fundamental states:

### 1. Stable Loading (Skeletons)
- Replaces spinners with pulse skeletons matching the exact geometry of expected cards and headers.
- Prevents layout shift (CLS = 0) during data loading.

### 2. Background Refresh
- Triggered when refreshing queries in the background.
- UI maintains existing interactive cards without jumping or resetting scroll position. A discreet indicator displays in the header or filter bar.

### 3. Genuine Empty State
- Rendered when a search or filter yields zero results (`total_count === 0`).
- Displays a helpful message (e.g. "لا توجد مقالات مطابقة للبحث المحدد") with a quick action to "إعادة ضبط المرشحات" (Reset Filters).
- Must NEVER be confused with network error states.

### 4. Network Error State
- Rendered when an API request fails (e.g., server offline, 500 error).
- Displays an alert banner with a human-readable Arabic explanation, the `X-Request-ID` for debugging, and a prominent "إعادة المحاولة" (Retry) button.
- Never displays a false "0 مقال" counter upon network errors.

### 5. Expired Session State (401)
- Intercepts 401 Unauthorized responses.
- Automatically clears stored user context, redirects to the login view, and stores the current path in state for post-login return.

### 6. Forbidden State (403)
- Rendered when a user attempts an action outside their role privileges (e.g., Viewer accessing user management).
- Explains the missing role requirement clearly without terminating the user session.

### 7. Action Confirmation Modals
- Mandatory for state-altering administrative actions:
  - Disabling a publisher source.
  - Demoting or disabling user accounts.
  - Revoking active sessions.
- Displays explicit action scope and cancel button.

### 8. Stale & Unknown Metadata State
- When an article has an unknown publication date (`published_at === null`), it displays an explicit badge "تاريخ النشر غير محدد" with reason tooltip, rather than substituting the fetch timestamp (Defect A13).

---

## 2. Responsiveness & Accessibility

- **Breakpoints:**
  - `360px` (Compact Mobile): Single-column feed, collapsible filter drawer, touch targets $\ge 44\text{px}$.
  - `768px` (Tablet): Two-column grid, compact header.
  - `1280px` (Desktop): Full workspace, sticky sidebar filters, reading pane.
  - `1440px` (Wide Desktop): Max-width bounded content ($1280\text{px}$) to prevent unreadable line lengths.
- **Accessibility:**
  - Visible focus indicator (`focus:ring-2 focus:ring-focus`) on all interactive buttons and inputs.
  - `dir="rtl"` logical spacing (`margin-inline-start`, `padding-inline-end`).
  - Screen reader attributes (`aria-expanded`, `aria-label`, `role="alert"`).
