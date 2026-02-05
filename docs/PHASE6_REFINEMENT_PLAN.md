# Phase 6 Refinement & Enhancement Plan

## 1. Quick Site Check Improvements
- **Problem**: Input `www.soa.org` fails (requires protocol).
- **Fix**: Update JS logic to auto-prepend `https://` if missing.
- **UI**: Add protocol selector or smart input handling.

## 2. Task Logging & History
- **Problem**: No "View Log" button, missing detailed stats (duplicates, failures).
- **Fix**:
    - Add "View Log" button to History table.
    - Implement log storage in `_task_history`.
    - Update Collectors to return stats: `{scanned, downloaded, duplicates, errors}`.
    - Display these stats in the history table/log modal.

## 3. Incremental Cataloging
- **Problem**: "Invalid collection type" error; KeyBERT usage confusion.
- **Fix**:
    - Add `catalog` to `valid_types` in `app.py`.
    - Verify `catalog_incremental.py` supports KeyBERT or fallback.
    - If user wants KeyBERT, ensure `categorize` function uses it (currently it uses OpenAI or regex rules). *Note: User said OpenAI is next week, so presumably use regex/KeyBERT if available.*

## 4. Simplified Scheduling
- **Problem**: Current global schedule required per-site config. User wants one global schedule for ALL sites.
- **Fix**:
    - Add `global_schedule` to `sites.yaml` (or just use a hardcoded default like daily 00:30 ET).
    - Refactor `init_scheduler` to create ONE job that runs "Scheduled Collection" for all sites sequentially (or parallel batches).
    - Timezone: Ensure server time is handled or offset for ET (UTC-5/4).

## 5. Export API Fix
- **Problem**: Internal Server Error (500).
- **Fix**: Debug `export_data` endpoint in `app.py`. Likely file-handle or SQL interaction issue.

## 6. Database/UI Enhancements
- **Files Page**:
    - Remove "Actions" column.
    - Make rows clickable -> Open "File Details" modal/page.
    - Add "Delete File" button (Soft delete: `status='deleted', deleted_at=...`).
- **AI Keyword Filter**:
    - **Problem**: "Data & Analytics" or "Risk & Capital" removed if not explicitly "AI".
    - **Fix**: Relax `is_ai_related` filter or add specific broad keywords ("Data", "Analytics", "Risk Modeling") to the allow-list. Implement case-insensitive logic.
- **Search Metadata**:
    - Add "Key Word Filter" to the UI (similar to Category filter).

## 7. Execution Order
1. Fix "Invalid collection type" (Blocking).
2. Fix Export 500 (Blocking).
3. Fix Quick Check URL (Usability).
4. Refactor Scheduler (Feature).
5. Update Database UI & Delete logic (Feature).
6. Update Log/Stats (Feature).
7. Relax AI Filter (Logic).
