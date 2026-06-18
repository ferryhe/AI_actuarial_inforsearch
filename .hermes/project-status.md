# Project Status

- Date: 2026-06-18
- Branch: `fix/guest-chat-login-entry`
- Scope: Fix guest Chat KB selection / explain-file flow and add compact top-right login entry.

## Current State

- PR-A / #156 through PR-I / #164 and docs refresh PR #165 are merged into `main`.
- Production guest QA found Chat regressions for non-logged-in users:
  - `/chat` showed no selectable KBs even though public Knowledge Bases listed ready KBs.
  - Guest chat sent questions to a missing Demo KB and returned `Visitor Demo knowledge base is not available`.
  - Database/File Detail “Explain with AI” redirected to Chat but failed with `Visitor chat is limited to the Demo knowledge base`.
- Root cause: backend visitor policy in `ai_actuarial/api/services/chat.py` filtered guest KB listing and forced/rejected guest queries based on `CHAT_VISITOR_DEMO_KB_ID` / default `demo`.
- Fix in progress removes the Demo-only visitor chat restriction while keeping guest chat quota enforcement; guests can list/select public ready KBs and send direct document context through Chat.
- Header login entry now stays visible as a compact top-right button on small screens.
- Sibling repositories remain out of scope.

## Verification

- Guest QA subagent on production before fix: confirmed database/category/file browsing work for guests; confirmed Chat KB selection and explain-file fail; no console errors observed.
- Read-only code investigation subagent: traced guest KB filtering and direct-document rejection to `ai_actuarial/api/services/chat.py`; located header login controls in `client/src/components/Layout.tsx`.
- Focused local verification after fix:
  - `python3 -m pytest tests/test_fastapi_chat_endpoints.py::test_visitor_chat_knowledge_bases_show_public_ready_kbs tests/test_fastapi_chat_endpoints.py::test_guest_equivalent_tokens_can_list_public_chat_kbs tests/test_fastapi_chat_endpoints.py::test_visitor_chat_knowledge_bases_do_not_depend_on_demo_kb_config tests/test_fastapi_chat_endpoints.py::test_visitor_chat_query_allows_selected_public_kb tests/test_fastapi_chat_endpoints.py::test_visitor_chat_query_allows_direct_document_context tests/test_auth_react_source.py -q`: 6 passed; existing SWIG deprecation warnings.
  - `python3 -m pytest tests/test_fastapi_chat_endpoints.py tests/test_auth_react_source.py tests/test_fastapi_auth_endpoints.py -q`: 47 passed; existing SWIG deprecation warnings.
  - `npm run build`: passed; Vite emitted the existing large-chunk warning.
  - `git diff --check`: passed.

## Local Notes

- Modified files: `.hermes/project-status.md`, `ai_actuarial/api/services/chat.py`, `client/src/components/Layout.tsx`, `tests/test_fastapi_chat_endpoints.py`, `tests/test_auth_react_source.py`.
- Existing protected stashes from earlier work remain untouched, including `protected-project-status-before-pr-f` and `protected-local-files-before-pr-d-review`.
- Next gate: independent review / Codex review, commit/push/open PR, inspect CI/Copilot comments, merge, deploy, and run production guest smoke.
