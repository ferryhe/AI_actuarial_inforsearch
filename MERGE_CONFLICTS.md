# Merge Conflicts with Main Branch

## Overview
There are merge conflicts between `copilot/implement-comments-adjustments` branch and `main` branch that need to be resolved before merging the PR.

## Conflicted Files

### 1. ai_actuarial/catalog_incremental.py

#### Conflict Location: Line ~145 (ORDER BY clause)

**Our Branch (copilot/implement-comments-adjustments):**
```python
    -- ORDER BY f.id ASC ensures deterministic, incremental processing
    -- (oldest files first). Alternative: DESC for newest files first.
    ORDER BY f.id ASC
    LIMIT ?
```

**Main Branch:**
```python
    ORDER BY f.id DESC
    LIMIT ?
```

**Analysis:**
- Our branch added documentation comments and uses ASC (oldest first)
- Main branch uses DESC (newest first)
- Need to decide which ordering is correct for the use case

#### Conflict Location: Lines ~267-363 (Processing logic)

**Our Branch:**
- Uses synchronous processing with `BEGIN IMMEDIATE`
- Processes rows one by one in a for loop
- Marks skipped items with `status="skipped"`

**Main Branch:**
- Uses `ThreadPoolExecutor` for parallel processing
- Implements `_process_single_row` helper function
- Converts sqlite rows to dicts for thread safety
- Batches writes at the end

**Analysis:**
- Main branch has significantly refactored the processing logic for performance
- Our branch focused on transaction safety (BEGIN IMMEDIATE) and status handling
- Both changes are valuable but need careful merging

### 2. ai_actuarial/web/app.py

**Expected Conflicts:**
- XSS vulnerability fixes in main
- SQL query fixes in main
- Our storage abstraction layer changes

**Analysis:**
- Main branch likely has security fixes that may overlap with our abstraction changes
- Need to review line-by-line to preserve both sets of improvements

## Recommended Resolution Strategy

### Option 1: Rebase on Main (Cleaner History)
```bash
git checkout copilot/implement-comments-adjustments
git rebase main
# Resolve conflicts
git push --force-with-lease
```

**Pros:**
- Linear history
- Easier to review
- Our changes appear as if made on top of main

**Cons:**
- Requires force push
- More complex conflict resolution

### Option 2: Merge Main into Branch (Safer)
```bash
git checkout copilot/implement-comments-adjustments
git merge main
# Resolve conflicts
git commit
git push
```

**Pros:**
- No force push needed
- Preserves original history
- Easier to undo if needed

**Cons:**
- Creates merge commit
- History is less linear

## Key Integration Points

### ThreadPoolExecutor + BEGIN IMMEDIATE
- Main's parallel processing conflicts with our BEGIN IMMEDIATE transaction
- Need to either:
  1. Keep parallel processing, adjust transaction strategy
  2. Keep single-threaded with BEGIN IMMEDIATE
  3. Implement a hybrid approach

### Status Handling
- Our `status="skipped"` logic needs to work with main's processing flow
- Main's `_process_single_row` returns status - integrate our skipped status there

### Storage Abstraction
- Ensure main's changes to web/app.py use our new abstraction methods
- Verify no new direct `_conn` access was introduced in main

## Files Modified in Both Branches

| File | Our Changes | Main Changes |
|------|-------------|--------------|
| catalog_incremental.py | BEGIN IMMEDIATE, skipped status, ORDER BY docs | ThreadPoolExecutor, DESC ordering, infinite loop fix |
| web/app.py | Storage abstraction, feature flags, file deletion | XSS fixes, SQL fixes, CSV export, job history, **REMOVED abstractions** |
| crawler.py | Added `_should_exclude_url` helper method | Added `stop_check` parameter, **REMOVED helper method** |
| storage.py | Added 7 abstraction methods | Added `deleted_at` column, `file_exists_by_hash` method |

## Critical Issues

### ⚠️ Main Branch Removed Our Abstractions!

**Problem:** The main branch appears to have:
1. Removed our `_should_exclude_url` helper from crawler.py
2. Reverted web/app.py to use direct `storage._conn` access instead of our abstraction methods

**Impact:**
- Our PR's main goal (eliminate direct _conn access) is being undone by main
- Code duplication is being reintroduced
- The abstraction layer we built is being bypassed

**Resolution Required:**
- Need to re-apply our abstraction methods on top of main's changes
- Ensure main's new features (CSV export, job history) use abstractions
- Verify main's XSS/SQL fixes are preserved while using our abstractions

## Next Steps

1. User decides on merge strategy (rebase vs merge)
2. Resolve conflicts preserving improvements from both branches
3. Run full test suite
4. Review security improvements from both branches
5. Update PR description with conflict resolution notes
