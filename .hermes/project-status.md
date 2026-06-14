# Project Status

- Date: 2026-06-14
- Branch: `feat/agentic-rag-summary-title-tools`
- Baseline: `origin/main` at `15edb62` (`Merge pull request #136 from ferryhe/feat/agentic-rag-manifest-registry-kb-ui`).
- Scope: PR3 — L0 ready_data summary/title search tools and basic question classifier.
- PR: pending creation for PR3.
- Previous PRs: [#136](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/136) — merged; [#135](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/135) — merged; [#134](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/134) — merged; [#133](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/133) (PR1 ready_data builder) — merged.

### Current State

- Local `main` was fast-forwarded to `origin/main` at `15edb62` after merging #136, then PR3 branch `feat/agentic-rag-summary-title-tools` was created from that baseline.
- Current plan position: PR0, PR1, the roadmap reconciliation PR, and PR2 are merged; PR3 implements L0 summary/title search tooling and FastAPI endpoints and is ready for pre-PR review/PR creation.
- Added ready-data search functions that read `ready_data_manifest.json`, `doc_catalog.jsonl`, optional `doc_summaries.jsonl`, and `sections.jsonl`; missing `doc_summaries.jsonl` falls back to catalog summaries, while missing/invalid ready-data files return empty tool results or API errors.
- Review follow-up tightened ready-data file access: manifest artifact paths are contained under the ready_data output directory; explicit and registry-resolved `output_dir` values must stay under the DB-adjacent `agentic_ready_data` directory; `output_dir` cannot be mixed with `kb_id` registry lookup.
- Added basic question classification for `catalog`, `locate`, `summary`, and `document_qa`; this intentionally does not implement PR4 alias-first rule/document-number lookup.
- Added `/api/agentic-rag/search/summaries` and `/api/agentic-rag/search/titles`; requests can pass explicit `output_dir` for tests or `kb_id`/`profile` to resolve a ready PR2 registry manifest.
- PR2 was merged as #136 at merge commit `15edb6252cd199776906924a9220cfec1c0d9034` after `python-smoke` passed and all 5 Copilot comments were addressed.
- PR2 remote gate after the wait window: GitHub `python-smoke` passed; Copilot left 5 inline comments. Four frontend comments requested i18n for Agentic manifest UI text, and one backend comment identified a valid `output_dir` rejection path that could leave/overwrite manifest state as `building`.
- Follow-up fixes address all 5 comments: frontend Agentic manifest labels, messages, buttons, and metadata now use existing `t(...)` translations; invalid `output_dir` requests are rejected before writing `building` registry state and are covered by a regression test that preserves an existing ready manifest.
- `gh pr view` GraphQL calls still return 401 in this environment; PR/check/review state was read with `gh pr checks` and REST `gh api`.
- PR2 deliberately keeps `kb_mode` as existing KB composition semantics (`manual`, `category`, `all`) and adds `manifest_profile` for Agentic ready_data profile selection. Standard/Agentic fallback is represented by manifest status/fallback metadata rather than overloading `kb_mode`.

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

### PR2 Delivery

- `ai_actuarial/storage.py`: added `agentic_ready_manifests` registry table and storage helpers for manifest upsert/list/get.
- `ai_actuarial/rag/knowledge_base.py`: added KB `manifest_profile` schema migration and create/get/list/update persistence.
- `ai_actuarial/agentic_rag/ready_data_builder.py`: added KB-scoped L0 builds via `kb_id`; when KB chunk bindings exist, sections are restricted to bound chunk sets to avoid cross-profile leakage.
- `ai_actuarial/api/services/rag_admin.py` and router: added manifest status/build APIs at `/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest` and `/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build`; list/detail KB payloads now include `agentic_ready_manifest`, fallback mode, stale/failed/missing/ready state, and output directory guardrails.
- `client/src/pages/Knowledge.tsx`: shows Agentic manifest status/fallback messaging on KB cards, adds build/rebuild button, and adds create-time `manifest_profile` selection.
- `client/src/pages/KBDetail.tsx`: shows manifest profile/status/count/output metadata and build/rebuild action on the KB detail page.
- Tests cover KB-scoped builder output, same-file multi-profile chunk leakage prevention, registry build/status/stale/failed paths, output directory traversal rejection, and frontend source contracts.

### PR3 Delivery

- `ai_actuarial/agentic_rag/ready_data_tools.py`: added `search_summaries` and `search_titles` over L0 ready-data files, stable result fields, ranking/limit behavior, missing-file tolerance, and catalog-summary fallback when `doc_summaries.jsonl` is absent.
- `ai_actuarial/agentic_rag/tools.py`: added basic `classify_question` with categories limited to `catalog`, `locate`, `summary`, and `document_qa`.
- `ai_actuarial/api/services/agentic_rag.py` and `ai_actuarial/api/routers/agentic_rag.py`: added read-side Agentic RAG summary/title search endpoints with explicit output-dir and PR2 manifest-registry resolution.
- `ai_actuarial/api/app.py`: includes the new Agentic RAG router before the retired `/api` fallback.
- Tests added in `tests/agentic_rag/test_ready_data_tools.py` and `tests/test_fastapi_agentic_rag_endpoints.py`, including artifact path containment, partial `doc_summaries.jsonl`, explicit output_dir containment, mixed `output_dir`/`kb_id` rejection, and not-ready registry status handling.

### Verification
- PR3 controller verification:
  - Worker implementation used TDD; initial red state was missing `ready_data_tools` module.
  - Spec-compliance reviewer found no PR3 scope gaps.
  - Code-quality reviewer found one critical path-containment issue and two important edge cases; all were fixed with regression tests.
  - `python -m py_compile ai_actuarial/agentic_rag/ready_data_tools.py ai_actuarial/agentic_rag/tools.py ai_actuarial/api/services/agentic_rag.py ai_actuarial/api/routers/agentic_rag.py ai_actuarial/api/app.py` (pass)
  - `python -m pytest tests/agentic_rag/test_ready_data_tools.py tests/test_fastapi_agentic_rag_endpoints.py -q` (16 passed)
  - `python -m pytest tests/agentic_rag/ tests/test_fastapi_agentic_rag_endpoints.py -q` (44 passed)
  - `FASTAPI_SESSION_SECRET=fastapi-entrypoint-temp-secret python -m pytest tests/test_fastapi_entrypoint.py -q` (7 passed)
  - `python -m pytest tests/test_fastapi_entrypoint.py -q` without a session secret returns 503 for health/migration endpoints because current local runtime has CSRF enabled and no default FastAPI session secret; this is an environment precondition, not a PR3 router regression.
  - `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
  - Mandatory `codex review --uncommitted` could not run because WindowsApps `codex.exe` returned `Access is denied`; worker self-check plus independent spec and code-quality reviewers were used as the available pre-PR review gate.
- PR3 worker verification:
  - `python -m pytest tests\agentic_rag\test_ready_data_tools.py tests\test_fastapi_agentic_rag_endpoints.py -q` (10 passed)
  - `python -m py_compile ai_actuarial\agentic_rag\ready_data_tools.py ai_actuarial\agentic_rag\tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py ai_actuarial\api\app.py` (pass)
  - `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py -q` (38 passed)
  - `git diff --check` (pass; Git emitted LF/CRLF working-copy warning for `ai_actuarial/api/app.py` only)
- PR2 local verification:
  - `python -m py_compile ai_actuarial/storage.py ai_actuarial/rag/knowledge_base.py ai_actuarial/agentic_rag/ready_data_builder.py ai_actuarial/api/services/rag_admin.py ai_actuarial/api/routers/rag_admin.py` (pass)
  - `python -m pytest tests/agentic_rag/test_ready_data_builder.py tests/test_fastapi_rag_admin_endpoints.py tests/test_knowledge_react_source.py -q` (38 passed)
  - `npm.cmd run build` (pass; Vite emitted existing large chunk warning)
  - `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
  - Multi-agent spec review found KB chunk scoping and stale scoping issues; both were fixed and covered by tests.
  - Multi-agent code-quality review found output_dir escape risk, stale metadata gap, and failed-build UI notice issue; all were fixed and covered by tests/source contracts.
  - Mandatory `codex review --uncommitted` could not run because WindowsApps `codex.exe` returned `Access is denied`; independent multi-agent spec and code-quality reviews were used as the available pre-PR review gate.
- PR2 post-review follow-up verification:
  - `python -m py_compile ai_actuarial/storage.py ai_actuarial/rag/knowledge_base.py ai_actuarial/agentic_rag/ready_data_builder.py ai_actuarial/api/services/rag_admin.py ai_actuarial/api/routers/rag_admin.py` (pass)
  - `python -m pytest tests/agentic_rag/test_ready_data_builder.py tests/test_fastapi_rag_admin_endpoints.py tests/test_knowledge_react_source.py -q` (38 passed)
  - `npm.cmd run build` (pass; Vite emitted existing large chunk warning)
  - `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
  - Mandatory `codex review --uncommitted` still cannot run because WindowsApps `codex.exe` returned `Access is denied`; the blocker remains recorded for the PR gate.
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
- PR3: document location and summary tools (`search_summaries` first, basic `search_titles`) + basic question classifier — pending PR creation
- PR4: L1 regulation manifest, aliases, alias-first `search_titles`, `search_sections`, `trace_relations`
- PR5a: backend Agentic loop core (`planner.py`, `agentic_loop.py`, `/api/agentic-rag/chat`, metadata trace)
- PR5b: Chat integration and frontend trace display with `rag_mode=agentic`
- PR6: L2 formula/actuarial manifest (`formula_cards`, structured tables, calculation terms, formula tools)
- PR7: eval loop and CI integration for retrieval/answer eval, citation coverage, hallucination checks, no-evidence refusal tests
