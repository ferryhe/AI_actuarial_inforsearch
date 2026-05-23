# Project Status

- Date: 2026-05-23
- Branch: codex/fix-document-explain-chat-payload
- Scope: Chat document explanation payload handling in the React chat page.
- Latest baseline: Merged origin/main after PR #107 landed.
- Changes: Document explain clicks now load markdown content and post document_content, document_filename, and document_file_url to /api/chat/query; added localized unavailable-content messages; added regression coverage.
- Review follow-up: Simplified the markdown response type and document loader to match the verified `/api/files/{file_url:path}/markdown` contract (`{ success, markdown }`) without a `data.markdown` fallback.
- Verification: python -m pytest tests/test_chat_react_source.py -q; python -m pytest tests/test_fastapi_chat_endpoints.py -q; npm.cmd run build.
- Latest follow-up verification: python -m pytest tests/test_chat_react_source.py -q; npm.cmd run build; git diff --check.
- Pre-PR review gate: Blocked because `codex --help` fails with `Program 'codex.exe' failed to run: Access is denied`.
- Merge readiness: Resolved post-PR-107 `.hermes/project-status.md` add/add conflict by preserving this PR's current status on top of origin/main.
- Browser smoke: Browser plugin rejected file:// dist/public/index.html by URL policy. Persistent local preview startup was blocked by the sandbox/process environment, so rendered browser QA remains unverified.
- Notes: No sibling repositories were read or modified.
