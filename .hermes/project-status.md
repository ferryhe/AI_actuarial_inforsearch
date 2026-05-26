# Project Status

- Date: 2026-05-26
- Branch: `fix/frontend-rbac-action-gates`
- Latest baseline: `origin/main` before this branch was created.
- Scope: Frontend RBAC action gates for Knowledge, KB detail, Database, Chat, and File Detail.
- Permission changes are UI-only in this PR: public/guest users keep read-only browsing/chat surfaces but no longer see or can use KB admin, persistent conversation management, export/download/delete/include-deleted, or task/chunk-generation controls without the matching permission.
- Knowledge/KB controls now distinguish `catalog.read` browsing, `tasks.run` indexing/pending task actions, and `config.write` management/configuration actions.
- Database controls now gate include-deleted and selection/delete behind `files.delete`, downloads behind `files.download`, and CSV export behind `export.read`; auth-loading is handled before URL rewrite/request generation so direct admin links preserve `include_deleted` until permissions are known.
- Chat now gates history/new/delete conversation UI and list API calls behind `chat.conversations`, while still preserving query-returned `conversation_id` for guest multi-turn context when only `chat.query` is available.
- FileDetail no longer checks nonexistent `rag.write`; task/chunk-generation controls use the actual backend `tasks.run` boundary while edit/download/delete controls continue to follow their specific permissions.
- Tests updated: added `tests/test_frontend_rbac_action_gates.py` and updated FileDetail source test to reject `rag.write`.
- Verification passed: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest tests/test_frontend_rbac_action_gates.py tests/test_auth_react_source.py tests/test_chat_react_source.py tests/test_file_detail_react_source.py -q` (19 passed).
- Verification passed: `npm run build`.
- Verification passed: `git diff --check`.
- Browser smoke passed with local FastAPI + Vite under auth-required guest mode: `/database` has no export/download/delete/include-deleted controls, `/knowledge` and KB detail show read-only browsing without create/delete/index/bind controls, `/chat` hides conversation history/new/delete while leaving document/chat UI, file detail shows write/download/delete/chunk controls disabled, and browser console has no JavaScript errors.
- Local Codex review gate: multiple rounds found auth-loading and permission-boundary issues; all accepted findings were fixed. Final Codex review found no discrete regressions.
- Next step: commit, push, create PR, then follow up on GitHub checks/review comments after the standard wait window.
