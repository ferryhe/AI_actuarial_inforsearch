# UI Improvement Plan

## Overview
This document outlines the planned improvements for the AI Actuarial Info Search web interface, focusing on user experience enhancements and functional improvements.

---

## 1. Task Modal Windows Enhancement

### 1.1 Modal Dialog Beautification
**Target:** First 5 tasks in Tasks page
1. **URL Collection** - Crawl specific URLs
2. **File Import** - Import local files  
3. **Web Search & Collect** - Search and download via Brave/Google
   - Supports both general search (no site filter) and site-specific search (with site filter)
4. **Quick Site Check** - Ad-hoc site scan without saving configuration
5. **Incremental Cataloging** - AI-powered categorization

**Changes:**
- Improve modal styling with better colors, shadows, and spacing
- Add clear icons for each task type
- Better form layout with consistent spacing
- Improved button styling (Start, Cancel)
- Add loading indicators when submitting

**After Submission:**
- Close modal automatically
- Return to Tasks homepage
- Auto-refresh page to show:
  - Updated Active Tasks section
  - New entry in History section with progress

**Files to modify:**
- `ai_actuarial/web/templates/tasks.html`
- `ai_actuarial/web/static/css/style.css` (if exists, or add inline styles)

---

## 2. Modal Z-Index Fix

### 2.1 Modal Background Behavior
**Problem:** Clicking outside modal causes it to go behind the page content

**Solution:**
- Ensure modal backdrop prevents clicks on underlying content
- Modal should either:
  - Stay on top (current click outside does nothing), OR
  - Close when clicking backdrop (user preference)

**Recommended approach:** Close modal on backdrop click (standard UX pattern)

**Implementation:**
```javascript
// Add click handler to modal backdrop
backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) {
        closeModal();
    }
});
```

**Files to modify:**
- `ai_actuarial/web/templates/tasks.html` (JavaScript section)

---

## 3. File Format Selection

### 3.1 Add Format Selector to 4 Tasks

**Target Tasks:**
1. **URL Collection**
2. **File Import**
3. **Web Search & Collect** (Note: Site Filter field should remain as optional)
4. **Quick Site Check**

**Important:** For Web Search & Collect task, the "Site Filter (Optional)" field must be preserved:
- When empty: General web search
- When filled: Site-specific search
- This single task supports both use cases

**UI Component:**
```html
<div class="form-group">
    <label>File Formats:</label>
    <div class="format-checkboxes">
        <label><input type="checkbox" name="formats" value="pdf" checked> PDF</label>
        <label><input type="checkbox" name="formats" value="docx"> DOCX</label>
        <label><input type="checkbox" name="formats" value="pptx"> PPTX</label>
        <label><input type="checkbox" name="formats" value="xlsx"> XLSX</label>
        <label><input type="checkbox" name="formats" value="html"> HTML</label>
    </div>
</div>
```

**Default:** PDF checked

**Backend Changes:**, fix card title to "Quick Site Check")
- `ai_actuarial/web/app.py` (handle format parameter)
- `ai_actuarial/collectors/url.py`
- `ai_actuarial/collectors/file.py`
- `ai_actuarial/search.py`

**Note:** In tasks.html, update Card 4 title from "Quick Check" to "Quick Site Check" for consistency.
- `ai_actuarial/web/templates/tasks.html` (add UI)
- `ai_actuarial/web/app.py` (handle format parameter)
- `ai_actuarial/collectors/url.py`
- `ai_actuarial/collectors/file.py`
- `ai_actuarial/search.py`

---

## 4. Database Search Improvements

### 4.1 Remove Keyword Filter

**Current:** Two separate fields
- Keyword Filter (text input)
- Search (text input)

**New:** Single search field
- Remove "Keyword Filter" input
- Keep only "Search" field for full-text search

**Files to modify:**
- `ai_actuarial/web/templates/database.html`
- `ai_actuarial/web/app.py` (remove keyword filter parameter from API)

---

### 4.2 Category Filter - Exact Match Logic

**Current behavior:** Unclear matching logic

**New behavior:** Case-sensitive exact match for category values
- Category field uses **semicolon-separated** values: `"AI; Risk & Capital; Pricing"`
- When filtering by "AI", match these patterns:
  - Exact match: `"AI"`
  - Start of list: `"AI; ..."`
  - Middle of list: `"...; AI; ..."`
  - End of list: `"...; AI"`

**SQL Pattern Matching:**
```sql
WHERE (
    category = 'AI' 
    OR category LIKE 'AI;%'
    OR category LIKE '%; AI;%'
    OR category LIKE '%; AI'
)
```

**Files to modify:**
- `ai_actuarial/web/app.py` (update category filter SQL logic)

---

## 5. Scheduled Task Management Improvements

### 5.1 Remove Web Search Tab

**Action:** Remove the "Web Search" tab from Scheduled Task Management page

**Files to modify:**
- `ai_actuarial/web/templates/scheduled_tasks.html`

---

### 5.2 Manual Trigger - Add Format Selection

**Action:** Add file format selector to manual trigger form (same as Task modals)

**UI:** Same checkbox group as defined in section 3.1
- Default: PDF checked
- Support multiple selection

**Files to modify:**
- `ai_actuarial/web/templates/scheduled_tasks.html`
- `ai_actuarial/web/app.py` (manual trigger handler)

---

### 5.3 Scheduled Task Configuration

**New Feature:** Global scheduled task configuration

**Location:** New section BEFORE "Configure Sites" on Scheduled Task Management page

**UI Structure:**
```
┌─────────────────────────────────────────┐
│ Scheduled Task Configuration            │
├─────────────────────────────────────────┤
│ Enable Scheduled Runs: [✓] Enabled     │
│ Schedule Type: [Daily ▼]               │
│ Run Time: [03:00] (24-hour format)     │
│ Run Sites: [✓] All configured sites     │
│ File Formats: [✓] PDF:** `config/sites.yaml`

**Structure to add:**
```yaml
# Existing content...
# (defaults, sites, etc.)

# New section at end of file
scheduled_tasks:
  enabled: true
  schedule_type: daily  # daily, weekly, monthly
  run_time: "03:00"     # 24-hour format
  run_day: null         # For weekly: "Monday", monthly: 1-31
  sites: "all"          # or list: ["SOA", "CAS"]
  file_formats: ["pdf", "docx", "pptx"]
  tasks:
    - type: update
      enabled: true
    - type: catalog
      enabled: true
      params:
        ai_only: false
        retry_errors: false
```

**Decision:** Use single configuration file (sites.yaml) for simplicity
**Recommendation:** **Option B (add to sites.yaml)**
- Pros: Single configuration file, easier management
- Cons: Mixing concerns (sites config + schedule config)

Alternative if separation preferred: **Option A**

**Active Task Display:**
- When scheduled task is configured, show in Active Tasks with status:
  - "Waiting to start (scheduled for 03:00)"
  - "Running" (when executing)
  - Move to History when complete
**Implementation Requirements:**
- Backend scheduler using `schedule` library (already in requirements.txt)
- Persistent state tracking in database (new table: `scheduled_task_runs`)
- Background worker thread in Flask app

**Files to create/modify:**
- `config/sites.yaml` (add scheduled_tasks section) OR
- `config/scheduled_tasks.yaml` (new file)
- `ai_actuarial/web/templates/scheduled_tasks.html` (add config UI)
- `ai_actuarial/web/app.py` (add config save/load endpoints)
- `ai_actuarial/scheduler.py` (new file - background scheduler)
- `ai_actuarial/storage.py` (add scheduled_task_runs table)

---

## Implementation Priority

### Phase 1: Quick Wins (1-2 hours)
1. Modal z-index fix (Section 2)
2. Remove keyword filter (Section 4.1)
3. Remove web search tab (Section 5.1)

### Phase 2: UI Enhancements (2-3 hours)
4. Modal beautification (Section 1)
5. Category filter exact match (Section 4.2)
6. Manual trigger format selection (Section 5.2)

### Phase 3: File Format Selection (3-4 hours)
7. Add format selectors to 4 task modals (Section 3)
8. Backend integration for format filtering

### Phase 4: Scheduled Tasks (4-6 hours)
## Summary of Key Decisions

✅ **Confirmed:**
1. 5 tasks to beautify: URL Collection, File Import, Web Search & Collect, Quick Check, Incremental Cataloging
2. 4 tasks get format selection: URL Collection, File Import, Web Search & Collect, Quick Check
3. Category separator: **Semicolon (;)** not comma
4. Configuration storage: **sites.yaml** (single file approach)
5. Modal closes on backdrop click (standard UX)

9. Design scheduled task configuration (Section 5.3)
10. Implement backend scheduler
11. Add UI for configuration
12. Test scheduled execution

---

---

## Summary of Key Decisions

✅ **Confirmed:**
1. **5 tasks to beautify:**
   - URL Collection
   - File Import
   - Web Search & Collect (with optional Site Filter)
   - Quick Site Check
   - Incremental Cataloging
   
2. **4 tasks get format selection:**
   - URL Collection
   - File Import
   - Web Search & Collect
   - Quick Site Check
   
3. **Name consistency:** Update card display to "Quick Site Check" (modal title already correct)

4. **Web Search task:** Single task with optional "Site Filter" field preserved
   - Empty = General search
   - Filled = Site-specific search

5. **Category separator:** Semicolon (;) with space after: `"AI; Risk & Capital"`

6. **Configuration storage:** `sites.yaml` (single file approach)

7. **Modal behavior:** Closes on backdrop click (standard UX)

---

## Testing Checklist

- [x] Modal opens correctly and stays on top
- [x] Modal closes on backdrop click
- [x] Task submission refreshes page and shows active task
- [ ] File format selection works for all 4 tasks (DEFERRED - See Implementation Report)
- [x] Database search works without keyword filter
- [x] Category filter matches exactly (case-sensitive with semicolons)
- [ ] Scheduled task configuration saves correctly (FUTURE WORK)
- [ ] Scheduled tasks appear in Active Tasks (FUTURE WORK)
- [ ] Scheduled tasks execute at configured time (FUTURE WORK)
- [ ] Manual trigger respects format selection (FUTURE WORK)

---

## Implementation Status

✅ **Phase 1 - Complete (100%)**
- Card 4 renamed to "Quick Site Check"
- Modal backdrop click-to-close verified
- Keyword filter removed from Database
- Web Search tab removed from Scheduled Tasks

✅ **Phase 2 - Complete (100%)**
- Category filter updated to semicolon-separated matching
- Modal beautification with animations and improved styling
- Auto-refresh after task submission

⏳ **Phase 3 - Deferred**
- File format selection feature requires extensive backend integration
- Documented as Priority 1 for next sprint
- See [UI_IMPLEMENTATION_REPORT.md](UI_IMPLEMENTATION_REPORT.md) for details

---

## Estimated Total Time
- Phase 1-2: 3-5 hours (immediate improvements)
- Phase 3-4: 7-10 hours (full feature implementation)
- **Total: 10-15 hours**
