# Project Status

- Date: 2026-05-25
- Branch: `feat/chat-rag-request-boundaries`
- Latest baseline: `origin/main` after PR120 permission split merged.
- Scope: PR5 security hardening request boundaries for Chat/RAG document context. Sibling repositories were not read or modified.
- Backend request boundary: `/api/chat` rejects `document_sources` payloads with more than 3 selected documents before quota/session work.
- Backend context boundary: user-selected document context is bounded to 15,000 characters per source and 45,000 characters total across the selected set.
- Backend UX metadata: when selected document content is clipped, assistant response metadata includes `context_truncated` plus `context_notice` with original/used/max char counts and truncated source names.
- Prompt safety: retrieved RAG passages and user-selected document contents are labeled as untrusted context and cannot override system/developer instructions, permissions, tools, safety rules, or formatting requirements.
- Frontend boundary: document comparison selection is capped at 3 files; additional toggles are disabled and show a localized limit message.
- Frontend UX metadata: if the API reports clipped context, the chat page shows a localized warning that extra text was automatically clipped.
- Tests: FastAPI chat tests cover >3 document rejection, truncation metadata, and untrusted context prompt wording.
- Tests: React source test covers the 3-file compare cap and clipping notice translations.
- Verification passed: `/home/ec2-user/.hermes/hermes-agent/venv/bin/python -m pytest tests/test_fastapi_chat_endpoints.py tests/test_chat_react_source.py -q` (24 passed, 3 warnings).
- Frontend build passed: `npm run build` from `client/`.
- Diff whitespace check passed: `git diff --check`.
- Local Codex review gate passed: `codex -c 'model="gpt-5.5"' review --uncommitted` completed with no discrete correctness/security/maintainability issues.
- Next step: commit, push, create PR for `feat/chat-rag-request-boundaries`; then start PR4 from latest `origin/main` after PR5 is open.
