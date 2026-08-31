# Project Status — Issue #274 Implementation

- Updated: 2026-08-30
- Repository: `AI_actuarial_inforsearch`
- Checkout: `C:\Project\AI_actuarial_inforsearch`
- Branch: `codex/issue-274-ask-ai` from `origin/main` at `1753f9800789`
- State: Issue #274 implementation and local verification complete; commit, push, PR, and delayed remote review audit are pending.

## Startup and boundaries

- Read `AGENTS.md`, the prior project status, Issue #274, and the complete applicable `graphify`, `karpathy-guidelines`, and browser skill instructions.
- Ran the required startup `git status --short --branch`, fetched latest `origin/main`, and created the fresh task branch `codex/issue-274-ask-ai` tracking that baseline.
- Only this repository was read or written. Sibling repositories remained off-limits.
- Pre-existing `graphify-out/` remains untracked and will not be committed.

## Implemented contract

- Added one canonical URL builder/parser for `/chat?kb_id=<encoded>&rag_mode=agentic`, rejecting blank, malformed, duplicate, extra, or unsupported parameters.
- Added Chat initialization that waits for the authorized Chat KB list, accepts only an exact available KB, applies one target once, re-applies a different target, and never sends a message or creates a conversation during initialization.
- Removed the Chat frontend Agentic Ready/manifest gate and stopped sending internal manifest profile fields. Agentic requests keep exactly one requested KB; the server continues to infer profile and silently fall back to Standard on that same KB.
- Added bilingual, accessible Ask AI actions to Knowledge cards and KB Detail. They require both `chat.view` and `chat.query` and are enabled only when the exact KB is present and not explicitly unusable in `/api/chat/knowledge-bases`.
- Added one fixed Ask AI action beside Browse Files on every Category card. It uses explicit `/api/rag/knowledge-bases` categories, ignores shared KBs, and enables only when exactly one dedicated KB exists and is Chat-available.
- Preserved Issue #272 customer-safe API/RBAC boundaries and added no endpoint, schema, role, quota, or conversation behavior.

## Files in scope

- `.hermes/project-status.md`
- `client/src/hooks/use-i18n.ts`
- `client/src/lib/navigation.ts`
- `client/src/lib/chat-knowledge-bases.ts`
- `client/src/pages/Categories.tsx`
- `client/src/pages/Chat.tsx`
- `client/src/pages/KBDetail.tsx`
- `client/src/pages/Knowledge.tsx`
- `client/src/pages/chat/routeTarget.ts`
- `tests/test_issue_274_ask_ai.py`
- `tests/test_chat_react_source.py`
- `tests/test_fastapi_chat_endpoints.py`

## Verification

- `npm run build`: passed; Vite transformed 2,146 modules. The repository's existing large-chunk advisory remains non-blocking.
- Focused Issue #274/frontend/RBAC/fallback pytest selection: `70 passed, 4 warnings`.
- `python -m ruff check tests/test_issue_274_ask_ai.py tests/test_chat_react_source.py`: passed.
- A broader Ruff invocation that included the full pre-existing `tests/test_fastapi_chat_endpoints.py` reported six unrelated existing E402/E731 findings outside the two payload lines changed for this Issue.
- `git diff --check`: passed, with only Git line-ending conversion notices.
- Browser smoke with a localhost mock API passed:
  - Knowledge showed enabled Ask AI for a Chat-available KB without a manifest and native disabled state for `usable=false`.
  - KB Detail showed the enabled Ask AI action.
  - Category Regulation (one dedicated plus one shared KB) enabled; Multiple (two dedicated) and Unavailable disabled.
  - Category click produced the exact canonical URL, Agentic mode, and exactly one selected KB.
  - Changing the initialized mode back to Standard remained stable for the same route target.
  - Captured request log contained zero `/api/chat/query` requests and zero conversation-creation POSTs.

## Working tree notes

- `graphify-out/` is the only unrelated untracked path and remains excluded.
- A temporary stash created solely to carry the prior project-status research note across branch creation still exists and is redundant after this status update.

## Recommended next action

- Review the final diff, commit the scoped files, push `codex/issue-274-ask-ai`, create a PR closing #274, then audit required checks and remote review/Copilot comments about 15 minutes later. Do not merge without explicit authorization.
