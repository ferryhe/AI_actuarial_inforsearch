# Project Status

- Date: 2026-06-14
- Branch: `feat/agentic-rag-eval-scaffolding`
- Baseline: `origin/main` at `3a0d5bd`.
- Scope: PR0 — Agentic RAG eval scaffolding + 20 baseline retrieval cases (per 飞书方案文档 PR0 路线).
- PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/134
- Previous PR: [#133](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/133) (PR1 ready_data builder) — merged.

### PR0 Delivery

- `ai_actuarial/agentic_rag/eval.py`: EvalCase/RetrievedItem/CaseResult dataclasses, SimpleKeywordRetriever (catalog_items + rag_chunks), RetrievalEvaluator, load_cases, CLI
- `eval/cases.jsonl`: 20 baseline cases covering exact lookup, keyword, empty, case-insensitive, top-k, partial word, Chinese/regulation/formula placeholders
- `scripts/run_agentic_retrieval_eval.py`: CLI entry point
- `tests/agentic_rag/test_eval.py`: 18 focused eval tests plus existing ready_data_builder coverage

### Verification
- Copilot PR review on #134 produced 12 unresolved comments; all were evaluated as in-scope and addressed.
- Follow-up fixes: programmatic usage docstring now names real exports; SimpleKeywordRetriever supports `close()` and context manager cleanup; rag chunk `RetrievedItem.score` matches ranking score; category matching handles semicolon-separated labels; no-expectation cases report retrieved doc IDs instead of `(no results)`; category metric docstrings were clarified; script shebang uses `python3`; the SOA case note no longer claims source_site is searched.
- `python -m pytest tests/agentic_rag/ -q` (23 passed: 18 eval + 5 ready_data_builder)
- `python -m ai_actuarial.agentic_rag.eval --help` (pass)
- `python scripts/run_agentic_retrieval_eval.py --help` (pass)
- `python -m py_compile ai_actuarial/agentic_rag/eval.py scripts/run_agentic_retrieval_eval.py tests/agentic_rag/test_eval.py` (pass)
- `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
- CLI JSON contract/idempotency verified with a temporary SQLite fixture: two `python -m ai_actuarial.agentic_rag.eval --db <fixture> --cases <fixture> --json` runs both returned 0 and parsed as JSON with 1/1 cases passing.
- Local default `python -m ai_actuarial.agentic_rag.eval --json` returned 1 in this checkout because `data/index.db` is a stale local DB with 0 rows in `files`, `catalog_items`, and `rag_chunks`; this is a local data fixture limitation, not a code regression.
- Remote CI before follow-up fixes: python-smoke ✅

### Design Notes
- Category-only cases require ≥1 category hit to pass (per Codex review fix)
- SimpleKeywordRetriever intentionally limited — measures baseline before agentic tools
- Retriever protocol allows swapping in vector/ready_data/agentic retrievers later

### Next PRs
- PR2: Manifest Registry + DB + KB UI
- PR3: search_titles / search_summaries API + question classifier
