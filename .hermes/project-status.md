# Project Status

- Date: 2026-05-25
- Branch: `feat/permission-split-sites-import`
- Latest baseline: `origin/main` after PR119 SSRF hardening merged.
- Scope: PR3 security hardening permission split for monitored-site maintenance and legacy server filesystem import. Sibling repositories were not read or modified.
- Backend authorization: Added `sites.write` and `files.import.server` to the canonical permission set. Admin retains the complete permission set; operator receives `sites.write` but not `files.import.server`.
- Backend authorization: Monitored site add/update/delete/import/export/sample and site backup list/create/restore/delete endpoints now require `sites.write` instead of `schedule.write`.
- Backend authorization: `/api/utils/browse-folder` now requires `files.import.server`, keeping legacy server filesystem browsing admin-only.
- Backend authorization: `/api/collections/run` rejects legacy `type=file` + `directory_path` requests for callers without `files.import.server`, while preserving safe upload-batch imports even if a stale `directory_path` field is present.
- Frontend authorization: Tasks page now hides the site configuration task card unless the caller has `sites.write`; scheduled-task controls remain gated by `schedule.write`.
- Tests: Permission unit tests cover operator `sites.write`, operator exclusion from `files.import.server`, and read-only tiers lacking both write permissions.
- Tests: FastAPI ops-write tests cover operator site maintenance, operator denial for backend settings/server-folder browse/legacy server-path imports, admin retention of server-path boundary behavior, and upload-batch imports with stale directory_path sanitized by runtime.
- Verification passed: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest tests/unit/test_permissions.py tests/test_fastapi_ops_write_endpoints.py tests/test_tasks_react_source.py -q && git diff --check` (54 passed, 3 warnings).
- Frontend build passed: `npm run build`.
- Local Codex review gate: first review found a stale `directory_path` + valid `upload_batch_id` regression; fixed and retested. Latest `codex -c 'model="gpt-5.5"' review --uncommitted` completed with no discrete correctness/security/maintainability issues.
- Next step: commit, push, create PR for `feat/permission-split-sites-import`, then check remote CI/Copilot comments after the requested 10-minute window.
