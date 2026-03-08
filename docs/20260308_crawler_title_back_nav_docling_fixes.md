# Crawler Title Selection, Back Navigation, Docling, and Database List Fixes — 2026-03-08

## Overview

This document records the design decisions and implementation details for four
bug-fixes and enhancements merged in the PR "Fix crawler title selection,
React back navigation, docling libxcb, and database list enhancements".

---

## Problem 1 — Crawler: institution name stored as document title

### Root cause

`_handle_file()` used `page_title` (the title of the HTML page that contained
the file link) as the document title.  Most institutions give each document its
own URL (e.g. `/publications/2025/epc-report`), so `page_title` is an excellent
title.  However, a handful of sites (HK Actuarial Society, Taipei Actuaries)
list every file on a single publications page.  For those sites
`page_title == cfg.name` (the institution's full name), producing useless titles
like "The Actuarial Society of Hong Kong" for every document.

There was also an unused signal: `_extract_links()` already returned
`(link, link_text)` pairs, where `link_text` is the anchor text of the
`<a>` tag.  That text is typically the most accurate, document-specific label
(e.g. "ASHK Newsletter Issue 01/2025").  But `_handle_file()` never received
this parameter.

### Fix — `ai_actuarial/crawler.py`

Three-tier title priority in `_handle_file`:

| Priority | Signal | Condition |
|----------|--------|-----------|
| 1 | `link_text` | Stripped anchor text; skipped if blank |
| 2 | `page_title` | Used only when it does **not** equal `cfg.name` (case-insensitive) |
| 3 | `original_filename` / URL basename | Always available |

```python
clean_link_text = link_text.strip() if link_text else None
useful_page_title: str | None = None
if page_title:
    site_name = (cfg.name or "").strip().lower()
    if not (site_name and page_title.strip().lower() == site_name):
        useful_page_title = page_title
title = clean_link_text or useful_page_title or original_filename or os.path.basename(parsed.path)
```

`link_text` is now passed from both link-loop call sites in `crawl_site` and
`scan_page_for_files`.

### Impact on existing sites

| Site type | Before | After |
|-----------|--------|-------|
| HK/Taipei (listing page) | Institution name (wrong) | Anchor text (correct) |
| Most other sites (per-doc page) | `page_title` (correct) | `page_title` still used (unchanged) |
| Direct file URL, no anchor | `page_title` or filename | Same fallback chain |

---

## Problem 2 — React FileDetail: back button always reset to page 1

### Root cause

Clicking a file in the React database list navigated to `/file-detail?url=…`
using `navigate()`.  The back button called `navigate("/database")`, which
always pushed a fresh `/database` route — page 1, no filters, no query.

### Fix

Two-part fix:

**`client/src/pages/FileDetail.tsx`** — `goBack()` helper:

```tsx
function goBack() {
  try {
    const ref = document.referrer;
    if (ref && new URL(ref).origin === window.location.origin) {
      window.history.back();
      return;
    }
  } catch {
    // URL parse failed — fall through
  }
  navigate("/database");
}
```

Uses `document.referrer` same-origin check rather than `window.history.length > 1`.
The `history.length` guard is unreliable because browsers include entries from
before the app was opened (e.g. when arriving from a bookmark), so it can be > 1
even when there is no in-app history to go back to.

**`client/src/pages/Database.tsx`** — URL state management:

All filter/page state is reflected in URL search params via
`window.history.replaceState()` on every change, and read back on mount.
Going back restores the exact page, query, sort, and filter combination.

---

## Problem 3 — Docling: `libxcb.so.1` crash on headless servers

### Root cause

Docling imports Qt, which tries to load the `xcb` X11 platform plugin even on
headless servers (no display attached).  The import failed with:

```
qt.qpa.plugin: Could not load the Qt platform plugin "xcb"
```

### Fix — `ai_actuarial/processors/docling.py`

```python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# ... docling import follows
```

`setdefault` is used so that an explicitly set environment variable is never
overridden.

---

## Problem 4 — React database list: feature parity with Flask UI

### Root cause

The Flask `database.html` template had two features missing from the React SPA:

1. An **Export CSV** button (visible to admin and operator).
2. A secondary line showing `original_filename` when it differs from the title.

### Fix — `client/src/pages/Database.tsx`

- **Export CSV**: button calls `GET /api/export?format=csv`.  Visible when
  `user.role` is `"admin"` or `"operator"`.
- **`original_filename` sub-line**: rendered beneath the title whenever the
  two values differ.
- Added i18n keys `db.export_csv` for English and Chinese.

### Backend permission alignment — `ai_actuarial/web/app.py`

A code review identified that the `export.read` permission was missing from
the `operator` and `operator_ai` role sets, causing the export API endpoint
(`/api/export`, decorated `@require_permissions("export.read")`) to 403 for
operators even though:

- The Flask template shows the export button for operators.
- The React UI exposes the button for operators.

Fix: `export.read` was added to both `"operator"` and `"operator_ai"` permission
sets, aligning the backend with the intended access policy reflected in the
Flask template.

---

## Testing

All 8 unit tests in `tests/test_crawler_allow_patterns.py` pass.

Python syntax validation of `app.py` passed (`ast.parse`).

Manual verification checklist:
- [ ] HK site crawl: titles show anchor text, not institution name
- [ ] Non-HK site crawl: titles still show `page_title` where descriptive
- [ ] FileDetail back button returns to correct list page/filters
- [ ] Export CSV button visible and functional for admin and operator
- [ ] Export CSV button hidden for non-admin/non-operator roles
- [ ] Docling import succeeds on headless server (no display)
- [ ] `original_filename` sub-line shown when it differs from title
