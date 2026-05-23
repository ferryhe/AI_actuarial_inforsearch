# Project Status

- Date: 2026-05-23
- Branch: codex/fix-document-explain-chat-payload
- Scope: Chat document explanation payload handling in the React chat page.
- Latest baseline: main fast-forwarded to origin/main at 71cb77e before branching.
- Changes: Document explain clicks now load markdown content and post document_content, document_filename, and document_file_url to /api/chat/query; added localized unavailable-content messages; added regression coverage.
- Verification: python -m pytest tests/test_chat_react_source.py -q; python -m pytest tests/test_fastapi_chat_endpoints.py -q; npm.cmd run build.
- Browser smoke: Browser plugin rejected file:// dist/public/index.html by URL policy. Persistent local preview startup was blocked by the sandbox/process environment, so rendered browser QA remains unverified.
- Notes: No sibling repositories were read or modified.
