
## Phase 2 Update (2025-02-04) - User Feedback & UX Improvements

### ✅ 1. Enhanced Exclusion & Deduplication
- **Constraint**: Previous logic downloaded excluded files (e.g., 'exam') if URL patterns didn't match.
- **Solution**: 
  - Added strict filename-based exclusion check (`_is_excluded` matches against `config/sites.yaml` rules).
  - Implemented SHA256 content hashing. Files with identical content (even if different names/URLs) are now skipped if they exist in the database.

### ✅ 2. Scheduled Tasks UI Overhaul
- **Constraint**: Basic manual trigger only, no configuration management.
- **Solution**: Rebuilt `scheduled_tasks.html` with:
  - **Tabs**: "Configured Sites", "Manual Trigger", and "Collection History".
  - **Site Management UI**: Add, Edit, and Search sites directly from the web interface (persisted to `sites.yaml`).
  - **Global Logs**: Added "View Global Application Log" feature to monitor system activity directly from the browser.

### ✅ 3. Improved File Import
- **Constraint**: User had to type absolute paths manually, which was error-prone.
- **Solution**: Added "Browse Folder" button using native OS dialogs (via backend bridge) for easier local directory selection.
