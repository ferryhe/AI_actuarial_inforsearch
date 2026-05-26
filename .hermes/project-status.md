# Project Status

- Date: 2026-05-26
- Branch: `fix/backend-public-rbac-tightening`
- Baseline: latest `origin/main` after PR A (`fix: gate frontend RBAC actions`) was merged.
- Scope: Backend RBAC/payload tightening for public file read payloads, deleted-file access, RAG/KB admin read endpoints, and config backup permissions.
- `/api/files` and `/api/files/detail` now project public responses through a public allowlist and only include sensitive fields (`sha256`, `local_path`, `etag`, `deleted_at`, `markdown_content`) for authenticated users with operational file/catalog permissions.
- Anonymous or unauthorized `include_deleted=true` requests are rejected (`401` for anonymous, `403` for authenticated users without `files.delete`).
- RAG/KB admin read endpoints are split by operational need: public KB browsing remains readable, pending-files and chunk profile reads are available to task runners, and category mapping/selectable/bindings admin surfaces require `config.write`.
- Config backup list/create/restore/delete endpoints now require `config.write` instead of `sites.write`.
- Tests updated for read payload filtering, include_deleted authorization, RAG admin endpoint permission split, config backup admin guard, and index dirty fixture consistency.
- Local verification completed so far: 49 selected tests passed, `git diff --check` passed, Codex CLI review passed after addressing findings about operator chunk profile reads and markdown availability for authenticated callers.
- Remaining before PR: service/browser smoke on current branch, commit/push, create PR, wait for remote comments/checks, then merge/delete branch if clean.
