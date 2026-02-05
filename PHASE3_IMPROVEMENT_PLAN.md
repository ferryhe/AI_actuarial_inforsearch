# PHASE 3 Improvement Plan: UX Refinement & Logic Hardening

This plan addresses immediate user feedback regarding the User Interface (colors, form logic, layout) and critical backend logic (fixing effective exclusion of unwanted files).

## 🎨 1. UI/UX Improvements (Display & Contrast)

### 1.1 Contrast Fix for File Detail Tags
- **Problem**: In the File Details page, tag labels and their background colors are identical or have poor contrast.
- **Action**: Modify CSS in `file_detail.html` (or separate CSS file) to ensure tag text is readable against the background (e.g., use dark text on light badges).

### 1.2 Hide Irrelevant Fields for Local Files
- **Problem**: "Original URL" and "Source Page" are meaningless for locally imported files but are currently shown.
- **Action**: Add conditional logic in `file_detail.html` to hide these fields when `source_site` is 'Local Import' or fields are empty.

### 1.3 Tooltips for Configuration Fields
- **Problem**: Users may not understand what "Max Depth", "Exclude Keywords", etc., mean.
- **Action**: Add an `(i)` icon next to these fields in:
  - Add/Edit Site Modal (`scheduled_tasks.html`)
  - Manual Trigger section (`scheduled_tasks.html`)
  - create these fields explaination in a tooltip file
  - **Behavior**: Click to toggle a help text block explaining the field.

### 1.4 File Details Layout
- **Reset Button**: Move the Reset button (likely mainly relevant in Database List view filters) to the far right.
- **Categories Display**: Ensure the File Details page explicitly lists the categories assigned to the file.

## 🛠️ 2. Scheduled Tasks & Configuration

### 2.1 Complete Site Configuration in UI
- **Problem**: "Edit Site" and "Add Site" modals currently miss fields like `exclude_keywords` and `exclude_prefixes`.
- **Action**: 
  - Update `api/config/sites` to return full site details.
  - Update `scheduled_tasks.html` modal to include inputs for:
    - `exclude_keywords`
    - `exclude_prefixes`
  - Ensure the "Sites List" displays these configurations (or a summary of them).

### 2.2 Manual Trigger Explanation
- **Action**: Add the same tooltip explanations (from 1.3) to the Manual Trigger form.

## 🛡️ 3. Critical Logic Fixes (Exclusion)

### 3.1 Fix Exclusion Logic Failure
- **Problem**: Files like `fall-2022-exam-erm-gc.pdf` are being downloaded despite 'exam' being an exclusion keyword.
- **Diagnosis**: 
  - The exclusion check might be happening on the *URL* before redirection or final filename resolution.
  - The check needs to be rigorously applied to the **final filename** after download but *before* database processing/saving.
- **Action**: 
  - Review and harden `Crawler._download_file` and `Crawler.crawl_site`. 
  - Ensure `exclude_keywords` are correctly passed from `SiteConfig`.
  - Add a final "safety check" on the local filename immediately after download. If it matches an exclusion rule, delete the file and skip processing. And exclude in the download history

## 🗄️ 4. Database Management & Search

### 4.1 "Oldest First" Sorting
- **Action**: Add a "Date (Oldest)" and normally used options to the sort dropdown in `database.html`.
- **Backend**: Update `api_files` in `app.py` to handle `sort=date_asc`.

### 4.2 "Uncategorized" Filter
- **Action**: Add an "Uncategorized" (or "Empty") option to the Category filter in `database.html`.
- **Backend**: Update search logic to filter for records where `categories` is null or empty list.

### 4.3 Auto-Refresh Filters
- **Action**: Add `onchange="searchFiles()"` (or equivalent) to the filter dropdowns in `database.html` so the list updates immediately without clicking "Search".

### 4.4 Category Filtering Logic
- **Problem**: Selecting a category currently might imply an "exact match" of the list rather than "contains".
- **Action**: Fix backend search logic. If a file has categories `['A', 'B']` and user filters for `A`, the file MUST show up. (Target: `ai_actuarial/search.py` or `app.py`).
