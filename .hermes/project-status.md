# Project Status

- Date: 2026-06-16
- Branch: `task/p1-2-chat-kb-first`
- Baseline: current branch created from `origin/main` per delegated task context.
- Scope: P1-2 Chat KB-first UI plus Chat API/types/session extraction.
- PR: [#152](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/152) — open; Copilot follow-up comments are being addressed in this branch.
- Previous PRs: [#151](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/151) — merged; no new post-#151 comments per task context.

## Current State

- Refactored `client/src/pages/Chat.tsx` so Chat contracts live in `client/src/pages/chat/types.ts`.
- Extracted Chat API endpoint calls into `client/src/pages/chat/api.ts`; API routes/contracts remain unchanged:
  - `/api/chat/conversations`
  - `/api/chat/knowledge-bases`
  - `/api/chat/available-documents`
  - `/api/chat/query`
  - `/api/files/{file_url}/markdown`
- Extracted conversation/session state and conversation load/create/delete helpers into `client/src/pages/chat/useChatSession.ts`.
- Updated the Chat left sidebar to be KB-first:
  - Knowledge base selection is now the primary left-sidebar entry with selectable KB rows and status/count labels.
  - Conversation history remains available below the KB section.
  - Documents are de-emphasized behind a smaller sidebar toggle rather than a first-class equal tab.
- Kept Agentic RAG backend untouched.
- Local `docker-compose.override.yml` still has an unrelated production override diff and must remain uncommitted.

## Verification

- `python3 -m pytest tests/test_chat_react_source.py tests/test_fastapi_chat_endpoints.py tests/test_fastapi_agentic_rag_endpoints.py -q` passed (54 tests; 3 pre-existing SWIG/import warnings).
- `npm run build` passed; Vite emitted the pre-existing large-chunk warning for the main bundle.
- `git diff --check` passed.
- `npx tsc --noEmit` was attempted and failed on pre-existing unrelated TypeScript errors in `client/src/pages/Settings.tsx`, `client/src/pages/tasks/ScheduleFromTaskButton.tsx`, and `client/src/pages/tasks/ScheduledTasksSection.tsx`; no Chat-specific TypeScript errors were reported before those existing errors stopped the command.

## Notes

- Sibling repositories remain out of scope for this project run.
- Do not copy secrets, `.env` files, generated credentials, active Docker volumes, logs, or local production overrides into this PR.
- No commit, push, or PR was performed per delegated task instruction.
