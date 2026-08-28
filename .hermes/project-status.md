# Project Status — Issue #256 Lightweight List APIs

- Updated: 2026-08-28
- Repository: `AI_actuarial_inforsearch`
- Branch: `codex/issue-256-lightweight-list-apis`
- Issue: `#256 fix: make Database and Knowledge list APIs lightweight`

## Implementation

- Knowledge-base list summaries now use bounded metadata/count queries. They do not load or validate `vector_json`, decode per-float embeddings, or compute the builder source fingerprint.
- Exact embedding identity, coverage, availability, compatibility, serving health, and the Ready summary remain in the compact list contract.
- `ready_build_input` is omitted from list responses and is loaded by the dedicated manifest/detail request when the user clicks Build. The server-side prelaunch fingerprint and publication guards remain authoritative.
- Database `/api/files` list SQL no longer selects or materializes markdown bodies on ordinary list requests. It projects `has_markdown` from compact catalog metadata, and every permission-level response omits `markdown_content`.
- Database markdown badges and Knowledge build actions consume the compact list rows; detail, preview, explain, markdown, export, and download routes remain unchanged.
- A realistic 8,704-row × 3,072-dimension fixture, multiple-KB fixture, SQL/decode traps, query counts, response-size assertions, and legacy/deep-guard regressions cover the bounded-work contract.

## Verification

- Managed review completed two accepted rounds. Round 1 found and fixed body materialization in the files query plus mismatched KB membership acceptance; round 2 returned `PASS`.
- Focused Issue/read/React tests: `python -m pytest -q -s tests/test_issue_256_lightweight_list_apis.py tests/test_fastapi_read_endpoints.py tests/test_database_react_source.py tests/test_knowledge_react_source.py` — `49 passed`.
- Ready/RAG regression: `python -m pytest -q tests/test_fastapi_rag_admin_endpoints.py tests/test_issue_238_kb_index_ready.py tests/test_ready_data_source_state.py tests/test_ready_data_publication.py` — `212 passed, 8 skipped` (220 collected).
- Large-fixture measurements: 8,704 embeddings at declared dimension 3,072; cold 97.3 ms, warm 104.2 ms, and 150 SELECT statements per list request; compact permission responses were 610–798 bytes in the regression fixture.
- Frontend: `npm run build` passed; only the existing chunk-size warning was emitted.
- Browser smoke in the default in-app browser passed for Database data rows/markdown badges, Knowledge Ready/coverage data, Build click, and View Details. The list did not request a manifest; Build triggered the dedicated manifest GET. The temporary fixture intentionally lacked production artifacts, so the existing readiness guard stopped the POST. No localhost application console error was observed; only unrelated browser-extension warnings appeared.
- `python -m compileall -q ai_actuarial/api/services/rag_admin.py ai_actuarial/api/services/read.py ai_actuarial/api/services/ready_data_publication.py ai_actuarial/storage.py` and `git diff --check` passed; only normal Windows line-ending warnings were emitted.

## Scope and next step

- No production deployment, production database, sibling repository, provider call, API key, or secret access was used.
- No general cache, identity change, publication-guard weakening, FTS redesign, or production rebuild was introduced.
- Next: complete the required independent Codex CLI pre-PR review, then commit, push, and open the Issue #256 pull request.

## Compact multi-KB batch follow-up

- `_KBListStorageView` now prepares all filtered list rows in one request-local batch and reuses exact KB/profile/publication/embedding maps in the existing list decorators and readiness state machine.
- `list_knowledge_bases` filters first, calls `prepare` once, and then decorates rows. List responses still omit `ready_build_input`; detail/build selectors and deep publication/source guards remain unchanged.
- Pre-fix invariant RED was 84 SELECTs for one KB and 216 for three KBs. Post-fix traced measurements are 37 SELECTs for one KB and 37 for three KBs, with zero `vector_json` SELECTs.
- Verification: exact invariant test passed; full Issue #256 module passed (8); focused list/read/React contracts passed (50); KB index/Ready Data regressions passed (212, 8 skipped); compileall and `git diff --check` passed.
- Worker did not commit, push, create/update a PR, merge, clean up, or access sibling/production resources. Next: manager review and persistence of the compact-batch worker report.

## Final pre-PR review assessment

- The fresh read-only gate returned `CHANGES`. The publication-history finding was accepted: the list batch must not select or decode every historical Ready publication; it may fetch only active/previous slot references plus the latest unpublished failed/validated attempt per exact KB/profile.
- The content-only/no-source markdown finding was rejected under the project review policy. It bypassed the formal markdown writer, while adding a body fallback to ordinary list SQL would violate the no-`markdown_content` AC and regression.
- Next: fix the accepted bounded-publication finding with a narrow RED/GREEN worker, rerun focused/deep checks, then repeat the fresh pre-PR gate. No commit or PR has been created.

## Final bounded-publication fix and gate

- `_KBListStorageView` now reads filtered Ready slots first and limits the single publication query to active/previous slot references plus the newest unpublished failed/validated attempt per `(kb_id, profile)`. Historical publication rows are neither selected nor JSON-decoded by the list path.
- The inherited history regression changed from RED to GREEN without weakening its sentinel: active, previous, and latest failed rows are decoded; an older failed row carrying the decode sentinel is not touched.
- Final verification: Issue #256 module `9 passed`; focused list/read/React group `51 passed`; Ready/publication/list-detail group `212 passed, 8 skipped`; one and three KB fixtures both used `37` SELECTs and zero vector reads; the 8,704 × 3,072 fixture completed in about `114 ms`; compileall and `git diff --check` passed.
- The final fresh read-only Codex CLI pre-PR gate returned `PASS` with no findings. Its own narrow pytest rerun could not create a temporary directory under the read-only sandbox, so the gate used the immediately preceding exact worker test evidence and verified that the worktree stayed unchanged.
- No production deployment/database, sibling repository, provider call, API key, or secret was used. Next: commit, push, open the Draft PR with exact Issue closure metadata, mark it Ready, then perform the single delayed remote-feedback/check pass.
