# Project Status

- Date: 2026-06-15
- Branch: `feat/agentic-rag-l2-formula-tools`
- Baseline: `origin/main` at `58cccb3` (`Merge pull request #140 from ferryhe/feat/agentic-rag-chat-ui-trace`).
- Scope: PR6 — L2 formula/actuarial ready_data manifest artifacts, formula/table/calculation-term read tools, and Agentic RAG read endpoints.
- PR: [#141](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/141) — open; remote checks/review gate pending.
- Previous PRs: [#140](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/140) — merged; [#139](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/139) — merged; [#138](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/138) — merged; [#137](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/137) — merged; [#136](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/136) — merged; [#135](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/135) — merged; [#134](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/134) — merged; [#133](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/133) (PR1 ready_data builder) — merged.

### Current State

- PR6 branch `feat/agentic-rag-l2-formula-tools` was created from merged PR5b baseline `58cccb3`.
- PR6 implementation target: formula profile ready_data should become buildable rather than a failed placeholder, with deterministic `formula_cards`, structured table, and calculation-term artifacts plus read tools/API endpoints that match existing Agentic RAG output-dir and KB registry resolution patterns.
- PR6 worker implementation commit `a7e6933` adds formula ready-data build support, formula/table/calculation-term read tools, formula search endpoints, planner/agentic-loop formula tool registration, rag-admin formula build success behavior, and focused tests.
- PR6 independent spec/code-quality reviewers found two valid Important follow-ups: L2 `relations_graph.json` did not validate formula/table/calculation-term targets against the new artifacts, and markdown tables with duplicate/blank headers could overwrite cells. Controller follow-up now validates L2 relation target IDs, disambiguates duplicate/blank table headers while preserving all cells, and adds CLI `--profile formula --validate` coverage.
- PR6 local verification after reviewer follow-up: `python -m pytest tests\agentic_rag\test_ready_data_builder.py -q` (13 passed); `python -m pytest tests\agentic_rag\test_ready_data_builder.py tests\agentic_rag\test_ready_data_tools.py tests\agentic_rag\test_planner_agentic_loop.py tests\test_fastapi_agentic_rag_endpoints.py tests\test_fastapi_rag_admin_endpoints.py -q` (81 passed); `python -m pytest tests\agentic_rag\ -q` (60 passed); `python -m py_compile ai_actuarial\agentic_rag\ready_data_builder.py ai_actuarial\agentic_rag\ready_data_tools.py ai_actuarial\agentic_rag\tools.py ai_actuarial\agentic_rag\planner.py ai_actuarial\agentic_rag\agentic_loop.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py ai_actuarial\api\services\rag_admin.py` (pass); `python -m ai_actuarial.agentic_rag.ready_data_builder --help` (pass; shows `--profile {general,regulation,formula}`); `git diff --check` (pass; LF/CRLF working-copy warnings only). Mandatory `codex review --uncommitted` remains blocked by WindowsApps `codex.exe` returning `Access is denied`; independent spec/code-quality reviewers were used as the available review gate.
- PR6 was opened as [#141](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/141) with head `b967c76`; remote checks/reviews are pending.
- PR5b branch `feat/agentic-rag-chat-ui-trace` was created from merged PR5a baseline `37d0a59` and merged as [#140](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/140) at merge commit `58cccb3`.
- PR5b in-progress changes add a compact Standard/Agentic RAG selector to Chat, route Agentic non-document questions through `/api/chat/query` with `rag_mode="agentic"` so quota/conversation/history persistence remain intact, map Agentic evidence into existing citation/retrieved-block rendering, and render `metadata.tool_trace` in an assistant-message trace details panel.
- Chat KB listing now returns each KB's `manifest_profile` and current `agentic_ready_manifest`, allowing the Chat UI to select Agentic-ready KBs by ready-data manifest status instead of standard vector index readiness.
- Agentic Chat is intentionally single-KB for PR5b: the UI enforces one ready Agentic KB in Agentic mode, and the backend rejects multi-KB Agentic chat before creating a conversation.
- Direct document explain/compare requests remain on the standard chat path; the backend rejects `rag_mode="agentic"` combined with direct document context before creating a conversation.
- Review follow-up addressed spec/code-quality findings around silent multi-KB truncation, missing Chat KB manifest metadata, Agentic-ready gating, and conversation/quota bypass.
- PR5b local verification after review follow-up: `python -m pytest tests\test_fastapi_chat_endpoints.py tests\test_fastapi_agentic_rag_endpoints.py tests\test_chat_react_source.py -q` (49 passed); `python -m py_compile ai_actuarial\api\services\chat.py` (pass); `npm.cmd run build` (pass; existing large chunk warning); `git diff --check` (pass; LF/CRLF working-copy warnings only). Browser smoke was attempted against a local Vite server but the in-app browser blocked `127.0.0.1`/`localhost` with `net::ERR_BLOCKED_BY_CLIENT`; CLI Vite startup and production build both succeeded. Mandatory `codex review --uncommitted` remains blocked by WindowsApps `codex.exe` returning `Access is denied`; independent spec/code-quality/post-fix reviewers were used as the available review gate.
- PR5b #140 remote gate before follow-up: GitHub `python-smoke` passed on head `e79e2ad`. Copilot left 5 valid inline comments. Follow-up fixes add Chat KB legacy-schema fallback when `manifest_profile` is absent, reject Agentic `document_sources` direct context before persisting a conversation, remove an unreachable Agentic KB guard, clarify the single-KB validation error, and move Agentic KB availability labels into i18n. Verification after Copilot follow-up: `python -m pytest tests\test_fastapi_chat_endpoints.py tests\test_chat_react_source.py -q` (32 passed); `python -m pytest tests\test_fastapi_chat_endpoints.py tests\test_fastapi_agentic_rag_endpoints.py tests\test_chat_react_source.py -q` (51 passed); `python -m py_compile ai_actuarial\api\services\chat.py` (pass); `npm.cmd run build` (pass; existing large chunk warning); `git diff --check` (pass; LF/CRLF working-copy warnings only). Mandatory `codex review --uncommitted` remains blocked by WindowsApps `codex.exe` returning `Access is denied`. GitHub inline reply attempts returned REST 404 for all 5 comments, so replies were skipped per user instruction. Follow-up remote `python-smoke` passed on head `b177ada`.
- PR5a branch `feat/agentic-rag-loop-core` was created from merged PR4 baseline `8ec5613` and merged as [#139](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/139) at merge commit `37d0a59`.
- Added deterministic planner `ai_actuarial/agentic_rag/planner.py` that maps `classify_question` categories to ordered ready-data tool steps and includes regulation-aware `search_sections` / `trace_relations` when profile is `regulation` or L1 artifacts are present.
- Added `ai_actuarial/agentic_rag/agentic_loop.py` runner that executes ready-data tools with bounded per-step limits, returns `query`, deterministic grounded `answer`, `evidence`/`results`, `metadata.tool_trace`, `kb_id`, `profile`, and `output_dir`, and uses a clear no-evidence fallback instead of hallucinating.
- Added `/api/agentic-rag/chat` through the existing Agentic RAG service/router resolution path, including explicit `output_dir`, `kb_id`/`profile`/`manifest_profile`, empty-query 400, and existing missing/not-ready registry errors.
- PR5a local verification passed before review follow-up: `python -m pytest tests\agentic_rag\test_planner_agentic_loop.py tests\test_fastapi_agentic_rag_endpoints.py -q` (22 passed); `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py -q` (66 passed); `python -m py_compile ai_actuarial\agentic_rag\planner.py ai_actuarial\agentic_rag\agentic_loop.py ai_actuarial\agentic_rag\tools.py ai_actuarial\agentic_rag\ready_data_tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py` (pass); `git diff --check` (pass; LF/CRLF working-copy warnings only).
- PR5a independent spec review found no spec gaps. Independent code-quality review found 3 Important issues; follow-up fixes now let unexpected ready-data tool exceptions surface as 500 instead of hidden no-evidence responses, dedupe evidence by document/section/relation identity while preserving `tools`/`sources` provenance, and only tolerate documented missing profile schema (`rag_knowledge_bases` table or `manifest_profile` column) while propagating other SQLite errors.
- PR5a post-review follow-up verification passed: `python -m pytest tests\agentic_rag\test_planner_agentic_loop.py tests\test_fastapi_agentic_rag_endpoints.py -q` (26 passed); `python -m py_compile ai_actuarial\agentic_rag\planner.py ai_actuarial\agentic_rag\agentic_loop.py ai_actuarial\agentic_rag\tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py` (pass); `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py tests\test_fastapi_rag_admin_endpoints.py -q` (93 passed); `git diff --check` (pass; LF/CRLF working-copy warnings only); mandatory `codex review --uncommitted` remains blocked by WindowsApps `codex.exe` returning `Access is denied`.
- PR5a #139 remote gate: GitHub `python-smoke` passed on head `d3e8863`. Copilot left 2 comments; the SQLite comment was already addressed by the local code-quality follow-up, which now only tolerates documented missing profile schema and propagates other SQLite errors. The `tool_trace` duplication comment was accepted; top-level `tool_trace` was removed so `metadata.tool_trace` is the canonical trace field, with a regression assertion. REST still lists the original inline comments, but they point at superseded diff hunks. Verification after Copilot follow-up: `python -m pytest tests\agentic_rag\test_planner_agentic_loop.py tests\test_fastapi_agentic_rag_endpoints.py -q` (26 passed); `python -m py_compile ai_actuarial\agentic_rag\planner.py ai_actuarial\agentic_rag\agentic_loop.py ai_actuarial\agentic_rag\tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py` (pass); `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py tests\test_fastapi_rag_admin_endpoints.py -q` (93 passed); `git diff --check` (pass; LF/CRLF working-copy warnings only); mandatory `codex review --uncommitted` remains blocked by WindowsApps `codex.exe` returning `Access is denied`.
- PR4 branch `feat/agentic-rag-l1-regulation-tools` was created from latest `main` after #137 merged, implements L1 regulation artifacts, read tools, read endpoints, and rag-admin regulation manifest build integration, and was merged as [#138](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/138).
- `ready_data_builder.build_l0(..., profile="regulation")` now emits the L1 profile artifacts declared in `manifest_profiles.py`: `doc_catalog.jsonl`, `title_aliases.jsonl`, `doc_summaries.jsonl`, `sections_structured.jsonl`, `relations_graph.json`, and `ready_data_manifest.json`. The existing L0 `general` manifest artifact list is unchanged.
- `search_titles` now checks `title_aliases.jsonl` first for exact/near alias, identifier, document-number, or rule-number matches, returning `source="title_aliases"` and `matched_alias` for alias hits before fallback scoring.
- Added `search_sections(query, output_dir, limit=...)` with stable document/section identity, heading, text snippet, score, and source fields. It prefers `sections_structured.jsonl` and falls back to L0 `sections.jsonl`.
- Added `trace_relations(query_or_doc, output_dir, limit=...)` over `relations_graph.json`; missing or invalid optional L1 artifacts return empty relation results or safe section fallback in the existing ready-data-tool style.
- Added `/api/agentic-rag/search/sections` and `/api/agentic-rag/trace/relations`, both using the existing Agentic RAG output-dir/KB registry resolution and `catalog.read` authorization dependency.
- Updated the rag-admin manifest build path so KBs with `manifest_profile="regulation"` can build ready L1 manifests through `/api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build`; `formula` remains a declared but not-yet-implemented profile and records a failed manifest.
- Review follow-up tightened PR4 behavior: `kb_id`-only Agentic search now resolves the KB's stored `manifest_profile`, generated L1 aliases include explicit `document_numbers` and `rule_numbers`, numeric alias matching uses bounded rule/document-number checks to avoid `Rule 7` matching `Rule 70`, and builder validation rejects manifest artifact path escapes plus orphan L1 structured-section/relation references.
- PR4 #138 remote gate: GitHub `python-smoke` passed; Copilot left 3 valid inline comments. Follow-up fixes avoid general-profile section-entry memory duplication, keep `text_snippet` within its max length contract, and replace relation expansion duplicate checks with a set-backed relation key lookup.
- Local `main` was fast-forwarded to `origin/main` at `ac35a8a` after merging #137, then PR4 branch `feat/agentic-rag-l1-regulation-tools` was created from that baseline.
- Current plan position: PR0, PR1, the roadmap reconciliation PR, PR2, PR3, PR4, PR5a, and PR5b are merged; PR6 is active on `feat/agentic-rag-l2-formula-tools`.
- Added ready-data search functions that read `ready_data_manifest.json`, `doc_catalog.jsonl`, optional `doc_summaries.jsonl`, and `sections.jsonl`; missing `doc_summaries.jsonl` falls back to catalog summaries, while missing/invalid ready-data files return empty tool results or API errors.
- PR3 remote review follow-up: Copilot correctly identified that partial `doc_summaries.jsonl` rows could mislabel catalog-only fallback hits as `source="doc_summaries"`. The search merge now tracks catalog and summary provenance per document and the partial-summary regression test asserts `source="doc_catalog"`.
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
- PR4 local verification:
  - TDD red state: focused pytest initially failed during collection because `search_sections` was not exported from `ready_data_tools`.
  - `python -m pytest tests\agentic_rag\test_ready_data_builder.py tests\agentic_rag\test_ready_data_tools.py tests\test_fastapi_agentic_rag_endpoints.py -q` (29 passed)
  - `python -m py_compile ai_actuarial\agentic_rag\ready_data_builder.py ai_actuarial\agentic_rag\ready_data_tools.py ai_actuarial\agentic_rag\tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py` (pass)
  - `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py -q` (51 passed)
  - Controller follow-up added rag-admin build integration for `manifest_profile="regulation"` and preserved failed-manifest behavior for `formula`.
  - `python -m py_compile ai_actuarial\agentic_rag\ready_data_builder.py ai_actuarial\agentic_rag\ready_data_tools.py ai_actuarial\agentic_rag\tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py ai_actuarial\api\services\rag_admin.py` (pass)
  - `python -m pytest tests\agentic_rag\test_ready_data_builder.py tests\agentic_rag\test_ready_data_tools.py tests\test_fastapi_agentic_rag_endpoints.py tests\test_fastapi_rag_admin_endpoints.py -q` (52 passed)
  - Independent spec/code-quality reviewers found registry profile resolution, typed alias-number fields, numeric alias false positives, validation path containment, and L1 referential validation gaps; all were fixed with regression tests.
  - `python -m pytest tests\agentic_rag\test_ready_data_builder.py tests\agentic_rag\test_ready_data_tools.py tests\test_fastapi_agentic_rag_endpoints.py -q` (33 passed)
  - `python -m pytest tests\test_fastapi_rag_admin_endpoints.py -q` (23 passed)
  - `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py tests\test_fastapi_rag_admin_endpoints.py -q` (78 passed)
  - `python -m ai_actuarial.agentic_rag.ready_data_builder --help` (pass; shows `--profile {general,regulation}`)
  - `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
  - Mandatory `codex review --uncommitted` still cannot run because WindowsApps `codex.exe` returned `Access is denied`; independent worker, spec reviewer, and code-quality reviewer were used as the available pre-PR review gate.
  - `git status --short --branch` showed only the PR4 modified files listed in this status update.
- PR4 #138 post-review follow-up verification:
  - GitHub remote gate before follow-up: `python-smoke` passed; Copilot left 3 valid inline comments about general-profile memory duplication, text snippet max-length contract, and relation expansion duplicate-check complexity.
  - `python -m pytest tests\agentic_rag\test_ready_data_tools.py tests\agentic_rag\test_ready_data_builder.py -q` (22 passed)
  - `python -m py_compile ai_actuarial\agentic_rag\ready_data_builder.py ai_actuarial\agentic_rag\ready_data_tools.py ai_actuarial\agentic_rag\tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py ai_actuarial\api\services\rag_admin.py` (pass)
  - `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py tests\test_fastapi_rag_admin_endpoints.py -q` (79 passed)
  - `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
  - Mandatory `codex review --uncommitted` still cannot run because WindowsApps `codex.exe` returned `Access is denied`; the blocker remains recorded for the PR gate.
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
- PR3 #137 post-review follow-up verification:
  - GitHub remote gate before follow-up: `python-smoke` passed; Copilot PR reviewer passed and left 2 valid inline comments about partial `doc_summaries.jsonl` source-label behavior and missing source assertion.
  - `python -m py_compile ai_actuarial\agentic_rag\ready_data_tools.py ai_actuarial\agentic_rag\tools.py ai_actuarial\api\services\agentic_rag.py ai_actuarial\api\routers\agentic_rag.py ai_actuarial\api\app.py` (pass)
  - `python -m pytest tests\agentic_rag\test_ready_data_tools.py tests\test_fastapi_agentic_rag_endpoints.py -q` (16 passed)
  - `python -m pytest tests\agentic_rag\ tests\test_fastapi_agentic_rag_endpoints.py -q` (44 passed)
  - `git diff --check` (pass; Git emitted LF/CRLF working-copy warnings only)
  - Mandatory `codex review --uncommitted` still cannot run because WindowsApps `codex.exe` returned `Access is denied`; the blocker remains recorded for the PR gate.
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
- PR3: document location and summary tools (`search_summaries` first, basic `search_titles`) + basic question classifier — merged as #137.
- PR4: L1 regulation manifest, aliases, alias-first `search_titles`, `search_sections`, `trace_relations` — merged as #138.
- PR5a: backend Agentic loop core (`planner.py`, `agentic_loop.py`, `/api/agentic-rag/chat`, metadata trace) — merged as #139.
- PR5b: Chat integration and frontend trace display with `rag_mode=agentic` — merged as [#140](https://github.com/ferryhe/AI_actuarial_inforsearch/pull/140).
- PR6: L2 formula/actuarial manifest (`formula_cards`, structured tables, calculation terms, formula tools) — active on `feat/agentic-rag-l2-formula-tools`.
- PR7: eval loop and CI integration for retrieval/answer eval, citation coverage, hallucination checks, no-evidence refusal tests
