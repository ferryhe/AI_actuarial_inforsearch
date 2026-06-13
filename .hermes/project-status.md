# Project Status

- Date: 2026-06-13
- Branch: `feat/agentic-rag-eval-scaffolding`
- Baseline: `origin/main` at `3a0d5bd`.
- Scope: PR0 — Agentic RAG eval scaffolding + 20 baseline retrieval cases (per 飞书方案文档 PR0 路线).
- PR: https://github.com/ferryhe/AI_actuarial_inforsearch/pull/134
- Previous PR: [#133](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/133) (PR1 ready_data builder) — merged.

### PR0 Delivery

- `ai_actuarial/agentic_rag/eval.py`: EvalCase/RetrievedItem/CaseResult dataclasses, SimpleKeywordRetriever (catalog_items + rag_chunks), RetrievalEvaluator, load_cases, CLI
- `eval/cases.jsonl`: 20 baseline cases covering exact lookup, keyword, empty, case-insensitive, top-k, partial word, Chinese/regulation/formula placeholders
- `scripts/run_agentic_retrieval_eval.py`: CLI entry point
- `tests/agentic_rag/test_eval.py`: 14 focused tests

### Verification
- `python -m pytest tests/agentic_rag/ -q` (19 passed: 14 eval + 5 ready_data_builder)
- `python -m ai_actuarial.agentic_rag.eval` (20/20, doc_hit_rate=100%, category_hit_rate=88.9%)
- Codex CLI review: 2 P1/P2 findings found and fixed
- CI: python-smoke ✅

### Design Notes
- Category-only cases require ≥1 category hit to pass (per Codex review fix)
- SimpleKeywordRetriever intentionally limited — measures baseline before agentic tools
- Retriever protocol allows swapping in vector/ready_data/agentic retrievers later

### Next PRs
- PR2: Manifest Registry + DB + KB UI
- PR3: search_titles / search_summaries API + question classifier
