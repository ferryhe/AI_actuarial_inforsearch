# Project Status — Issue #297 Preview Sensitive Fields

- Updated: 2026-08-30
- Repository: `AI_actuarial_inforsearch`
- Worktree: `C:\Users\ferry\.codex\worktrees\issue-297\AI_actuarial_inforsearch`
- Branch: `agent/issue-297`
- Baseline HEAD / merge-base / `origin/main`: `3bb3ebde3bd0d144ba054ae736d9515707d95041`
- State: fresh read-only reviewer round 1 passed with no valid finding; review-cycle state is `local_review_complete`. Changes remain intentionally uncommitted for manager publication.

## Startup and boundaries

- Read the complete project `AGENTS.md`, prior `.hermes/project-status.md`, `karpathy-guidelines`, and `graphify` instructions before editing.
- Startup branch was `agent/issue-297` tracking `origin/main`; the worktree was clean.
- Only the assigned Issue #297 worktree is writable. The controller checkout, its untracked `graphify-out/`, sibling repositories, secrets, checkout-external review state, branches, PRs, and remotes are off-limits.
- The assigned worktree had no existing `graphify-out/graph.json`. A rebuild was excluded because it would create out-of-scope artifacts and require subagents, which this task explicitly forbids. Read-only `rg`, source inspection, and `git blame/log` were used for the same-shaped call-site audit.

## Corrected acceptance interpretation

- Authorization is capability-based through the existing `routers.read._can_view_sensitive_file_fields(AuthContext)` helper, not hard-coded role names.
- Anonymous and authenticated callers whose existing helper result is false (covered by a `guest` token with `files.read` but no sensitive capability) must not receive any field in `SENSITIVE_FILE_FIELDS`.
- Registered and premium currently have `files.download`, so the existing helper returns true for them. They retain `local_path` and `sha256`, as do operator and admin. No permission matrix or existing read/download contract changed.
- Client query parameters, headers, and GET bodies cannot opt into sensitive fields; only the resolved `AuthContext` controls the service flag.

## Implementation

- `api_rag_files_preview` now retains the parsed `AuthContext`, reuses `_can_view_sensitive_file_fields`, and passes only that result to the service.
- `get_rag_file_preview` now accepts `include_sensitive: bool = False`. Its default is fail-closed.
- The preview service reuses `services.read.SENSITIVE_FILE_FIELDS` and removes every listed field from `file_info` unless the trusted service flag is true.
- Public preview markdown, chunk-set selection, chunk payload, route status, and public file metadata remain unchanged.

## Regression evidence

- Valid pre-fix RED command:
  - `python -m pytest tests/test_fastapi_file_preview.py -k "hides_sensitive_fields_by_default or sensitive_fields_follow_existing_capability_gate" -q`
  - Result: `2 failed, 4 deselected`; both failed specifically because `file_info` exposed members of `SENSITIVE_FILE_FIELDS` (`local_path` and `sha256`).
- Post-fix GREEN with the same selector:
  - Result: `2 passed, 4 deselected`.
- The regression covers:
  - service invocation with the default flag hides all `SENSITIVE_FILE_FIELDS`;
  - anonymous API preview remains 200 and preserves public URL/markdown while hiding sensitive fields;
  - authenticated guest with query/header/body self-assertions still cannot enable sensitive fields;
  - registered, premium, operator, and admin retain the correct stored `local_path` and `sha256` because the existing capability helper returns true.

## Same-shaped call-site audit

- `services.read.list_files` and `get_file_detail`: already use default-false `include_sensitive` and the same router helper; no change needed.
- `get_file_chunk_sets` and `generate_file_chunk_sets`: use `get_file_by_url` only for existence checks and do not return the file record; excluded.
- `get_downloadable_file`: returns a file stream rather than file metadata and requires `files.download`; excluded.
- `update_file_record` and `export_catalog`: return complete records but their routes require `catalog.write` and `export.read`; current authorized roles are helper-true operator/admin, so they are outside the public preview defect and its AC; excluded.
- `delete_file_record`: uses the path internally under `files.delete` and does not return the path/hash; excluded.
- Import-batch `sha256`: describes newly uploaded batch output under `tasks.run`, not a stored-file preview projection; excluded.
- `get_rag_file_preview`: the sole `file_info` projection with the missing gate; fixed.

## Local review

- Fresh read-only reviewer round 1 completed with PASS.
- The reviewer reported no valid in-scope finding, so no follow-up code or test change was required.
- Review-cycle state is `local_review_complete`.

## Verification results

- Manager final focused preview plus existing read-contract suite:
  - `python -m pytest tests/test_fastapi_file_preview.py tests/test_fastapi_read_endpoints.py -q`
  - Result: `12 passed` with four pre-existing dependency deprecation warnings.
- Manager CI FastAPI smoke selection: `13 passed`.
- Manager Agentic eval tests: `31 passed`.
- Manager CLI eval: `3/3 passed`.
- Capability facts used by the corrected AC:
  - `python -m pytest tests/unit/test_permissions.py -k "registered_has_download or premium_has_full_task_view" -q`
  - Result: `2 passed, 18 deselected`.
- Non-gating broader permission-file check:
  - `python -m pytest tests/unit/test_permissions.py -q`
  - Result: `19 passed, 1 failed`; the unrelated existing test constructs `request.headers` as a plain dict while current `deps._session_cookie_values` calls `.getlist()`, causing `AttributeError`. Neither file is touched by Issue #297, so no out-of-scope fix was made.
- Touched-file Ruff:
  - `python -m ruff check ai_actuarial/api/routers/files_write.py ai_actuarial/api/services/files_write.py tests/test_fastapi_file_preview.py`
  - Result: `All checks passed!`
- Touched-file compile:
  - `python -m py_compile ai_actuarial/api/routers/files_write.py ai_actuarial/api/services/files_write.py tests/test_fastapi_file_preview.py`
  - Result: passed.
- `git diff --check`: passed; Git emitted only checkout line-ending notices.
- Manager final Ruff, touched-file `py_compile`, and `git diff --check` all passed.
- Frontend files were not changed, so a frontend build was not required.

## Current next action

- Manager should commit and push the reviewed changes, create the Draft PR, and then mark it Ready under the authorized Issue-to-merge workflow. This worker must not commit, push, create or modify a PR, merge, delete branches, or remove the worktree.
