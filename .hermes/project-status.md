# Project Status

- Date: 2026-06-14
- Branch: `main`
- Baseline: `origin/main` at `c9dea4b`.
- Scope: Post-PR0/PR1 roadmap reconciliation; next implementation scope is PR2 — Manifest Registry + DB + KB UI.
- PR: [#134](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/134) — merged 2026-06-14 12:27 UTC.
- Previous PR: [#133](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/133) (PR1 ready_data builder) — merged.

### Current State

- Local `main` matches `origin/main` at merge commit `c9dea4b` (`Merge pull request #134 from ferryhe/feat/agentic-rag-eval-scaffolding`).
- GitHub open PR list is empty; no PR2/PR3 branch or open PR was found.
- Current plan position: PR0 is complete and merged; next implementation step is PR2.
- Remote PR0 feature branch was not returned by `git ls-remote`, so it appears to have been removed after merge.

### External Plan Reconciliation

- Original Feishu source `https://my.feishu.cn/docx/EceldD7lIojOyaxzqjkczbo7neh` is still blocked by Lark CLI app/auth configuration, but the same plan was supplied as a local DOCX attachment and read successfully on 2026-06-14.
- Plan title: `ai_actuarial_inforsearch 现有信息转成 Agentic RAG 独立项目方案（修订版）`; parsed content had 205 paragraphs and 16 tables.
- Plan PR0 expectation: eval scaffolding, 20 retrieval cases, top-k/doc/category hit reporting, no ready_data dependency. Current #134 satisfies this and is merged.
- Plan PR1 expectation: L0 ready_data builder MVP with basic validate, headings-only extraction, `doc_catalog.jsonl`, `doc_summaries.jsonl`, `sections.jsonl`, and `ready_data_manifest.json`; plan text also names `store.py` and `extractors.py`.
- Current #133 PR1 reality: merged L0 MVP delivered `ready_data_builder.py`, `manifest_profiles.py`, `doc_catalog.jsonl`, `sections.jsonl`, `ready_data_manifest.json`, validation, and tests. It does not currently have separate `store.py` / `extractors.py` modules or `doc_summaries.jsonl`; decide whether to fold those into PR2/PR3 or explicitly keep PR1 as the narrower MVP.
- Plan PR2 is still next: `agentic_ready_manifests` table, KB `manifest_profile` field, Knowledge UI manifest status/build button, KB mode selection rules, fallback behavior for KBs without ready_data, and stale/failed manifest messaging.
- Plan PR3 follows PR2: `ready_data_tools.py`, `tools.py`, `search_summaries`, basic `search_titles`, `/api/agentic-rag/search/summaries`, `/api/agentic-rag/search/titles`, and basic question classifier (`catalog`, `locate`, `summary`, `document_qa`).
- Plan acceptance table omitted a PR2 row. Local PR2 acceptance baseline should be: registry schema/migration works, KB manifest profile/status persists, Knowledge UI shows manifest status, build button triggers/records manifest build outcome, Standard/Agentic/Professional/Hybrid KB selection and no-ready_data fallback rules are implemented, and stale/failed manifest states have tests or smoke coverage.
- Plan decision: PR3 remains L0 summary/title search only. Do not promise rule-number/document-number/attachment alias-first locate top-3 >= 90% until PR4.

### PR0 Delivery

- `ai_actuarial/agentic_rag/eval.py`: EvalCase/RetrievedItem/CaseResult dataclasses, SimpleKeywordRetriever (catalog_items + rag_chunks), RetrievalEvaluator, load_cases, CLI
- `eval/cases.jsonl`: 20 baseline cases covering exact lookup, keyword, empty, case-insensitive, top-k, partial word, Chinese/regulation/formula placeholders
- `scripts/run_agentic_retrieval_eval.py`: CLI entry point
- `tests/agentic_rag/test_eval.py`: 18 focused eval tests plus existing ready_data_builder coverage

### Verification
- Copilot PR review on #134 produced 12 unresolved comments; all were evaluated as in-scope and addressed.
- Follow-up fixes: programmatic usage docstring now names real exports; SimpleKeywordRetriever supports `close()` and context manager cleanup; rag chunk `RetrievedItem.score` matches ranking score; category matching handles semicolon-separated labels; no-expectation cases report retrieved doc IDs instead of `(no results)`; category metric docstrings were clarified; script shebang uses `python3`; the SOA case note no longer claims source_site is searched.
- Independent pre-merge agent review found doc/category metric semantics and `top_k <= 0` edge cases; fixes added so doc hit rate is independent from category-only failures, category-only cases pass on category hits without requiring `min_hits=0`, expected category denominators use split labels, and non-positive top-k returns no results.
- `python -m pytest tests/agentic_rag/ -q` (27 passed: 22 eval + 5 ready_data_builder)
- `python -m ai_actuarial.agentic_rag.eval --help` (pass)
- `python scripts/run_agentic_retrieval_eval.py --help` (pass)
- `python -m py_compile ai_actuarial/agentic_rag/eval.py scripts/run_agentic_retrieval_eval.py tests/agentic_rag/test_eval.py` (pass)
- `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
- CLI JSON contract/idempotency verified with a temporary SQLite fixture: two `python -m ai_actuarial.agentic_rag.eval --db <fixture> --cases <fixture> --json` runs both returned 0 and parsed as JSON with 2/2 cases passing, `doc_hit_rate=1.0`, and `category_hit_rate=1.0`.
- Local default `python -m ai_actuarial.agentic_rag.eval --json` returned 1 in this checkout because `data/index.db` is a stale local DB with 0 rows in `files`, `catalog_items`, and `rag_chunks`; this is a local data fixture limitation, not a code regression.
- Remote CI after follow-up fixes: `python-smoke` passed.
- GitHub review threads on #134 still show unresolved Copilot housekeeping in the UI; most are outdated after follow-up commits. The remaining non-outdated details fallback comment was checked against current code and the retrieved-items case is handled by the `retrieved:` fallback.
- Mandatory local `codex review --uncommitted` gate could not run because WindowsApps `codex.exe` returned `Access is denied`; independent multi-agent review was used as the available pre-merge review path.

### Design Notes
- Category-only cases require ≥1 category hit to pass (per Codex review fix)
- SimpleKeywordRetriever intentionally limited — measures baseline before agentic tools
- Retriever protocol allows swapping in vector/ready_data/agentic retrievers later

### Next PRs
- PR2: Manifest Registry + DB + KB UI
- PR3: document location and summary tools (`search_summaries` first, basic `search_titles`) + basic question classifier
- PR4: L1 regulation manifest, aliases, alias-first `search_titles`, `search_sections`, `trace_relations`
- PR5a: backend Agentic loop core (`planner.py`, `agentic_loop.py`, `/api/agentic-rag/chat`, metadata trace)
- PR5b: Chat integration and frontend trace display with `rag_mode=agentic`
- PR6: L2 formula/actuarial manifest (`formula_cards`, structured tables, calculation terms, formula tools)
- PR7: eval loop and CI integration for retrieval/answer eval, citation coverage, hallucination checks, no-evidence refusal tests
