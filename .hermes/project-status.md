# Project Status

- Date: 2026-05-24
- Branch: `feat/browser-file-import-batches`
- Latest baseline: latest `origin/main` when this branch was created.
- Scope: PR1 security hardening for browser-selected local file import batches. Sibling repositories were not read or modified.
- Backend: Added `/api/files/import-batches` multipart upload endpoint gated by `tasks.run`; uploaded files are staged under an import-batch root with per-file/total limits, path traversal checks, owner checks, duplicate relative-path checks, and an allowlist covering supported import extensions including EPUB.
- Backend: Immediate file collections now require `upload_batch_id`; `directory_path` is rejected and removed from task payloads so the server no longer imports arbitrary server filesystem paths from user input.
- Backend: Runtime file collection consumes staged batch file paths and applies the selected extension filter during collection. Browser-selected original relative paths and filenames are preserved for staged files.
- Backend: Scheduled `file` tasks are rejected server-side because browser upload batches are one-shot immediate imports and cannot be safely replayed by the scheduler.
- Frontend: File import UI now uses browser file/folder pickers plus `FormData`, removes the server-side `FolderBrowser`, filters selected files by the chosen extensions before upload, and disables scheduling for file imports.
- Frontend i18n: Added Chinese/English strings for browser-based file upload labels, hints, errors, and uploading state.
- Local browser smoke passed on Vite/FastAPI: `/tasks` as operator, opened File Import, uploaded a PDF plus TXT sidecar batch through `/api/files/import-batches`, launched `/api/collections/run` with `upload_batch_id`, and confirmed task completion with no browser console errors.
- Verification passed: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest tests/test_fastapi_ops_write_endpoints.py tests/test_fastapi_ops_read_endpoints.py tests/test_tasks_react_source.py -q` (39 passed, 3 warnings).
- Verification passed: `npm run build` (passed with existing Vite large-chunk warning).
- Verification passed: `git diff --check` (passed).
- Local Codex review gate: first run found valid issues around scheduled file tasks and upload allowlist; fixes were applied. Final `codex -c 'model="gpt-5.5"' review --uncommitted` completed with `No discrete, actionable correctness issues`.
- Next step: commit, push, create PR1, then check CI and remote comments before moving to PR2 SSRF protection.
