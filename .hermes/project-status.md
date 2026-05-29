# Project Status

- Date: 2026-05-29
- Branch: `fix/kb-admin-session`
- Baseline: latest `origin/main`.
- Scope: Fix RAG knowledge-base write endpoints so logged-in admin/operator browser sessions can create, update, delete, categorize, bind files/chunks, and start KB indexing without being blocked by the legacy `CONFIG_WRITE_AUTH_TOKEN` service-layer check.
- RAG write routes now pass the resolved auth context into the service layer; the service trusts already-authorized session/API-token contexts and only falls back to `CONFIG_WRITE_AUTH_TOKEN` when no route auth was provided.
- Legacy `CONFIG_WRITE_AUTH_TOKEN` compatibility is scoped to RAG write routing through `require_rag_write`; it is not promoted globally in shared auth dependencies and does not authorize unrelated config/task endpoints.
- Focused tests added for anonymous 401, registered 403, operator/admin session success, legacy RAG token success, and unrelated config write denial with the legacy token.
- Verification completed locally: `git diff --check`; `python -m pytest tests/test_fastapi_rag_admin_endpoints.py -q` (16 passed); `python -m pytest tests/test_fastapi_auth_endpoints.py tests/test_fastapi_ops_write_endpoints.py -q` (37 passed).
- Independent review gate completed: delegate review PASS, delegate focused verification PASS, Codex CLI pre-PR review PASS. Codex read-only pytest attempt could not start due sandbox temp-dir limitation, but local pytest runs above passed.
- PR #128 follow-up on 2026-05-29: addressed Copilot's note by preserving `tasks.run` for `create_index_task` while keeping the scoped legacy RAG token fallback; focused auth/RAG tests pass locally.
