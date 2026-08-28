# Project Status — Issue #254 Canonical Chat Document Titles

- Updated: 2026-08-28
- Repository: `AI_actuarial_inforsearch`
- Branch: `codex/issue-254-canonical-chat-titles`
- Baseline: `6e98b1253e80df6536f32e5fe878678aa93f5b36`
- Issue: `#254 fix: use canonical document titles across Chat references and Documents`

## Reproduction and delivery

- Reproduced immutable index metadata without a title yielding `unknown`, the Documents/explain/comparison UI preferring filename, and historical citations remaining stale after catalog title changes.
- Chat response and history read boundaries now resolve current `files.title` and `files.original_filename` in one batch query, preserving separate fields and avoiding N+1 queries.
- Standard RAG, direct-document/comparison, and Agentic evidence use canonical current titles for prompts and returned references without changing immutable chunks, indexes, embeddings, or historical message JSON.
- Missing/deleted records fall back to a valid original filename or decoded URL basename; empty and case-insensitive `unknown` values fall through to localized neutral UI labels.
- One React helper drives Documents, explain/comparison prompts, citations, retrieved blocks, and history. Document search continues to match both curated title and original filename.

## Verification

- Managed review closed after three rounds: rounds 1–2 findings were fixed with targeted RED/GREEN tests; round 3 passed. Authoritative `review_count=3`.
- Focused Chat/API/frontend/chatbot regression command passed: `131 passed`.
- Required `python-smoke` local equivalent plus Agentic eval tests passed: `44 passed`; deterministic Agentic eval passed `3/3` with full citation coverage and no unsupported answers.
- Frontend production build passed (`2138` modules); compileall and `git diff --check` passed apart from Windows line-ending warnings.
- In-app Browser smoke passed for canonical Documents display, title and filename search, explain/comparison prompts, historical citation and retrieved-block re-enrichment, fresh title edits, missing-file URL basename, and English/Chinese neutral fallbacks. Browser console errors were empty.
- Independent `codex review --uncommitted` ran against the complete diff, independently passed the 55 focused tests and production build, and performed read-only sibling/history checks. It did not return a final review verdict after about eight minutes and was interrupted to avoid an unbounded gate; this tooling non-convergence is recorded as the pre-PR review blocker. Its unrelated baseline `tsc --noEmit` errors are outside #254.

## Scope and current state

- Changes are limited to Chat API presentation/read enrichment, Chat UI display naming/i18n, and focused regressions.
- No mutable title was added to retrieval metadata, no KB index/chunk/embedding or historical message was rewritten, and no catalog edit semantics, production operation, secret, sibling repository, or graphify output was touched.
- Implementation, TDD, three-round managed review, required tests/build, and Browser smoke are complete. Draft PR publication and the remote review/check lifecycle are next, with the Codex CLI non-convergence disclosed.
