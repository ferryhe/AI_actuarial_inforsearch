# PHASE 4 Improvement Plan: Advanced Features & Persistence

This plan focuses on refining data filtering, UI aesthetics, task management stability, and integrating global search capabilities.

## 🎨 1. UI Refinement & Fixes

### 1.1 Category Filter Logic
- **Issue**: Selecting a category like "AI" currently matches widely (matches "cl**ai**m") because of a simple `LIKE %term%` query.
- **Action**: Update `api_files` filtering logic.
  - Ensure "Whole Word" matching for comma-separated category strings.
  - Implement precise matching (e.g., matching `AI` vs `Claim` vs `Paid`).

### 1.2 File Details Contrast
- **Issue**: The labels "Source Site", "Original URL", etc., in the File Details view have poor contrast (text color matches background).
- **Action**: Update `file_view.html` / `style.css`.
  - Ensure table headers (`<th>`) have a distinct background color (e.g., light gray `#f8f9fa`) and dark text (`#333`) to stand out from the white content cells.

### 1.3 Local Import Interaction Redesign
- **Issue A (Visual)**: The result modal covers the entire browser and lacks design.
  - **Action**: Reskin the modal to be a centered, standard dialog box with proper padding, shadows, and backdrop.
- **Issue B (Data)**: Results show "undefined" for files found/cataloged.
  - **Action**: Fix `api_import_results` response to structure keys correctly (`files_found`, `files_cataloged`, `duplicates`, `errors`) and ensure the JS reads them accurately.
- **Issue C (Flow)**: Clicking "OK" should keep user on the Import interface.
  - **Action**: Prevent page reload or redirect upon closing the modal.

## ⚙️ 2. Task Management & Stability

### 2.1 Task History "Details" Button
- **Issue**: Clicking "Detail" on the Dashboard's Recent Task list does nothing, unlike the functionality in the Schedule page.
- **Action**:
  - Wire up the "Detail" button in `index.html` to open the Log Modal.
  - Ensure it fetches the correct log ID/content.

### 2.2 Optimize Dashboard Polling
- **Issue**: Active Tasks panel refreshes too frequently.
- **Action**: Increase the polling interval in `index.html` / `main.js` to 10-20 seconds to reduce server load and visual jitter.

### 2.3 Stop Running Tasks
- **Issue**: No way to abort a running crawler/job.
- **Action**:
  - Add a "Stop" / "Terminate" button to the Active Tasks list.
  - Implement a backend endpoint `/api/tasks/stop/<job_id>`.
  - Update `JobManager` to handle cancellation signals (threading events or process termination).

### 2.4 Job History Persistence
- **Issue**: Task history is lost upon server restart (currently in-memory only).
- **Action**:
  - Migrate Job History to a persistent store.
  - **Option**: Save to `data/job_history.jsonl` or a SQLite table `task_history`.
  - Load history from disk on application startup.

## 🔎 3. Global Search Integration

### 3.1 Web Search Interface
- **Issue**: The implemented "Brave/SerpAPI" search logic is not accessible via UI.
- **Action**: Add a new "Web Search Discovery" section in `scheduled_tasks.html` (or a dedicated tab).
  - **Inputs**:
    - Search Scope: "Global" (All Web) or "Target Site" (site:example.com).
    - Keywords.
    - Search Engine Selection (if multiple configured).
  - **Backend**: Connect to `ai_actuarial.search` and `collectors.adhoc` to trigger a discovery job.
