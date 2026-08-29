# Project Status — Issue #263 Search Acquisition Outcomes

- Updated: 2026-08-28
- Repository: `AI_actuarial_inforsearch`
- Branch: `codex/issue-263-search-acquisition-outcomes`
- Baseline: `71a3d173d0d10addc9e4e28b86c10af02f334217`
- Issue: `#263 fix: make search-result acquisition failures explicit and auditable`

## Implementation

- Added a small shared search-acquisition outcome contract with the nine required terminal dispositions, finite subreasons, bounded counters/reasons, URL normalization, query/fragment secret redaction, and shared summary/log formatting.
- Kept `Crawler.scan_page_for_files(...)->list[dict]` compatible and added `scan_page_for_files_with_outcome()` for API/CLI consumers. Initial request failures, link download failures, storage failures, redirects/content-type mismatches, duplicates, filters, stops/timeouts, and empty eligible sets now produce explicit outcomes.
- `TaskRuntime._run_search_task()` consumes only the shared outcome channel. It writes complete bounded `acquisition_outcomes` and `acquisition_summary`, logs every raw discovery result plus a final summary, fails all-error runs, preserves mixed successes with warnings, and treats duplicate/filter-only runs as completed no-ops with skipped counts.
- Both `cmd_update()` search branches use one shared consumer and the same summary. No CLI arguments or command names changed.
- The direct scheduled collector contract remains unchanged, including `site_results.classification=http_403`.

## Round 1 accepted findings

- Fresh replacement CLI worker continued the ended ephemeral implementation session (`no rollout found`) under manager authorization. All seven Round 1 findings were accepted; none were rejected.
- Restored baseline list-API exception behavior: initial request failures and linked-download failures remain silent, while direct downloads, direct/linked handlers, page-content handlers, and storage failures propagate to `URLCollector`. Only `scan_page_for_files_with_outcome()` converts those propagated failures to terminal outcomes.
- Linked-file duplicate aggregation now counts and selects the real `url`, `normalized_url`, or `content_hash` subreason. The same-shaped page-content content-hash path was confirmed affected and now records `content_hash` too.
- Added a private staging-I/O marker around local directory creation and staging-file open/write/read boundaries, so local `OSError` failures become `storage_failed/storage` while response/socket failures remain `download_failed/network`.
- Staged direct/linked downloads now read only a 16 KiB sample and reuse the existing access-wall classifier before mismatch classification, covering challenge/login/cookie/JavaScript responses.
- Added stop checks after the initial request, during streaming, after direct/linked download, and before handler persistence. Stopped downloads remove `.part` files and terminate as `stopped_or_timeout/stopped` without saving.
- CLI site parsing and the site-search branch now propagate the existing `collect_linked_files` and `collect_page_content` values. Both CLI search branches still share the same outcome consumer; the unrelated global-search CLI semantics were not expanded.
- Crawler success, duplicate, and page-content acquisition logs now pass URL values through `safe_outcome_url()` without adding a new logging framework.

## Round 2 accepted findings

- `cmd_update()` now retains the shared acquisition summary and returns nonzero only when search outcomes contain failures with no downloads. Zero discovery, duplicate/filter/no-eligible no-ops, and mixed download-plus-failure runs remain exit 0.
- Known document extensions now validate their declared MIME type. Missing `Content-Type` and `application/octet-stream` remain allowed, while incompatible types such as `text/plain` and `image/png` produce `redirect_or_content_type_mismatch/content_type`. Existing direct and linked HTML access-wall classification still runs before mismatch classification.
- Ordinary non-artifact navigation links no longer increment `filtered/extension`. Extension filtering remains for recognized document extensions that are disallowed by the site configuration, and normalized-URL/content-hash duplicate subreasons are no longer overridden by navigation links.
- CLI site search now merges and case-insensitively deduplicates site/default exclusions with `search.exclude_keywords`, matching the existing runtime behavior. The unrelated global-search exclusion inputs remain unchanged.
- Page-content collection now uses the shared exact/normalized URL lookup before extracting or hashing content, preserving `url` versus `normalized_url` subreasons.
- Manager-rejected Round 2 finding 4 was intentionally not changed: `no_eligible_file_found` remains `failed=0` and a successful no-op because it is not an access/download/storage operational failure.

## Round 3 accepted findings

- Search acquisition now checks for a stop immediately after HTML text parsing and again before each `_handle_page_content()` / `_handle_file()` persistence call. Direct and linked staged files are removed when a late stop arrives, and the terminal outcome is `stopped_or_timeout/stopped`.
- CLI `_site_configs()` now applies the shared `coerce_bool()` semantics to `collect_linked_files` and `collect_page_content`, including quoted YAML values such as `"false"` and `"true"`, while absent values remain `None`.
- Local staging-file flush/close `OSError` is now converted to `_StagingIOError`, yielding `storage_failed/storage`. Response-body `read()` failures remain `download_failed/network`.
- A single discovery page with both saved and failed linked files now keeps the downloaded count while using the representative operational failure disposition, subreason, HTTP status, and safe failed-link URL. Runtime remains successful with warnings when downloads are nonzero; CLI remains exit 0 and logs the mixed outcome at warning level; disposition totals reconcile with the outcome count.

## Fresh pre-PR repair

- A linked-file storage lookup `OSError` is now caught inside the aggregation loop. Earlier saved items remain in the report, the failure is recorded as `storage_failed/storage`, and the existing mixed-outcome path reports `downloaded=len(new_items)` with `failed=1`.
- The equivalent linked lookup sites are covered: URL lookup before download, content-hash lookup after staging, and URL/content-hash lookup after a handler returns no item. Staged `.part` files are removed for the two post-download lookup failures.
- `scan_page_for_files()` retains its list return and exception contract: the new lookup catches re-raise in legacy mode. Runtime and CLI require no consumer code change; a real mixed storage report produces the same shared summary and remains successful/exit 0.
- Direct raw or redirect-final URLs with a recognized document extension outside configured `file_exts` now return `filtered/extension` before HTML processing. The classifier reuses `DEFAULT_FILE_EXTS`; an unknown `.zip` suffix remains `no_eligible_file_found/empty`.

## TDD evidence

- Initial RED: `python -m pytest -q -s tests/test_issue_263_search_acquisition_outcomes.py tests/test_scheduled_collector.py` collected 16 tests and produced `11 failed, 5 passed`. Failures covered 5×403, duplicates, absent structured channel, mixed/no-result metadata, safe bounded output, CLI parity, stop, and content-hash/mismatch behavior. The five passes were legacy-list compatibility and four scheduled-collector regressions.
- Supplemental RED: storage lookup, downloaded-filename filtering, and redirect/content-type mismatch — `3 failed`; after the narrow fix — `3 passed`.
- Supplemental RED: fragment secret redaction and runtime exclude-prefix propagation — `2 failed`; after the narrow fix — `2 passed`.
- Self-review RED: two-branch CLI result logs used a false running total (`1/1`, `2/2`) — `1 failed`; after logging outcomes with the final count — `1 passed`.
- Self-review RED: runtime pre-filtering reduced two identical 403 rows plus one off-domain row to one outcome — `1 failed` (`total=1`, expected `3`); after moving domain filtering into the shared crawler outcome channel — `1 passed` with two requests and three terminal outcomes.
- Focused GREEN before final regression: `python -m pytest -q tests/test_issue_263_search_acquisition_outcomes.py` — `18 passed`.
- Round 1 precise RED on the fresh worker: 18 selected tests produced `15 failed, 3 passed`. The failures mapped one-for-one to the seven accepted findings; the three passes preserved legacy successful-list, initial-request-silent, and linked-download-silent behavior.
- Round 1 targeted GREEN after the narrow fixes: the same 18 selected tests produced `18 passed`.
- Full Issue #263 specialty GREEN after Round 1: `34 passed`.
- Round 2 precise RED: the 18 new/extended cases produced `9 failed, 9 passed, 3 warnings`. The failures were 2 CLI all-failure branches, 2 incompatible MIME types, 3 navigation/duplicate cases, 1 site-exclusion classifier parity case, and 1 normalized page-content duplicate case. The nine passing guards covered zero/duplicate/filter/no-eligible/mixed CLI exits, missing/octet-stream MIME, recognized disallowed extension filtering, and exact page-content URL duplication.
- Round 2 targeted GREEN after the five surgical fixes: the identical 18 cases produced `18 passed, 3 warnings`.
- Full Issue #263 specialty GREEN after Round 2: `51 passed, 3 warnings`.
- Round 3 precise RED: seven focused cases produced `6 failed, 1 passed, 3 warnings`. The failures covered quoted CLI flag coercion, post-HTML stop, late direct and linked pre-persistence stops, staging close classification, and single-page mixed linked failure metadata. The passing guard confirmed response `read()` `OSError` remained a network failure.
- Round 3 targeted GREEN after the four narrow fixes: the identical seven cases produced `7 passed, 3 warnings`.
- Full Issue #263 specialty GREEN after Round 3: `57 passed, 3 warnings`.
- Fresh-repair Finding 1 RED: `python -m pytest -q tests/test_issue_263_search_acquisition_outcomes.py::test_linked_storage_lookup_failure_keeps_prior_item_in_crawler_runtime_and_cli` — `1 failed, 3 warnings`; the report returned `items=[]` instead of the already-saved item.
- Fresh-repair Finding 2 RED: `python -m pytest -q tests/test_issue_263_search_acquisition_outcomes.py::test_direct_disallowed_document_extension_is_filtered tests/test_issue_263_search_acquisition_outcomes.py::test_unknown_direct_extension_is_not_misclassified_as_filtered` — `2 failed, 1 passed, 3 warnings`; direct and redirect-final DOCX cases returned `no_eligible_file_found`, while the unknown-extension guard passed.
- Fresh-repair targeted GREEN: the mixed lookup, two direct-extension cases, and unknown-extension guard produced `4 passed, 3 warnings`; the two staged same-shaped lookup guards separately produced `2 passed, 3 warnings`.

## Verification

- The prior 126-test API/crawler/collector/logging/stop/read selection plus 16 new Round 1 tests now collects `142`; result: `142 passed, 4 warnings`. Warnings were dependency deprecations only.
- Direct `URLCollector` regression plus scheduled collector rerun: `6 passed, 3 warnings`.
- `python -m compileall -q` over all touched Python modules/tests passed.
- `python -m ai_actuarial update --help` passed and still exposes only the existing `--no-search` option. No JSON CLI/schema/idempotency contract was added or changed.
- `git diff --check` passed; only normal Windows line-ending warnings were emitted.
- Current Round 2 related regression selection collected `159`; result: `159 passed, 4 warnings`. Warnings were the existing SWIG and Starlette dependency deprecations.
- Current direct legacy-list/`URLCollector` plus scheduled collector focus collected `6`; result: `6 passed, 3 warnings`, including unchanged scheduled `http_403` behavior.
- Current `python -m compileall -q ai_actuarial/cli.py ai_actuarial/crawler.py ai_actuarial/task_runtime.py ai_actuarial/search_acquisition.py tests/test_issue_263_search_acquisition_outcomes.py tests/test_task_stop_support.py` passed.
- Current `python -m ai_actuarial update --help` passed and still exposes only `--no-search`; the duplicate-no-op CLI case covers the existing idempotent outcome, and no `--json` or schema contract exists for this command.
- Current `git diff --check` passed with only the existing CRLF conversion warnings.
- Round 3 crawler/runtime/task-stop/scheduled regression selection (`test_crawler_request_policy.py`, `test_crawler_allow_patterns.py`, `test_url_safety.py`, `test_task_stop_support.py`, and `test_scheduled_collector.py`) passed: `66 passed, 3 warnings`.
- Round 3 focused scheduled collector plus legacy list/`URLCollector` rerun passed: `6 passed, 3 warnings`, preserving scheduled direct-download `http_403` and legacy exception behavior.
- Round 3 `python -m compileall -q ai_actuarial` passed.
- Round 3 `python -m ai_actuarial --help` and `python -m ai_actuarial update --help` passed; no CLI arguments changed.
- Round 3 `git diff --check origin/main` passed with only normal Windows line-ending warnings.
- Fresh-repair full Issue #263 specialty suite passed: `63 passed, 3 warnings`.
- Fresh-repair crawler/request-policy/allow-pattern/URL-safety/task-stop/scheduled regression selection passed: `66 passed, 3 warnings`, including all four scheduled collector cases.
- Fresh-repair `python -m compileall -q ai_actuarial tests/test_issue_263_search_acquisition_outcomes.py tests/test_task_stop_support.py` passed.
- Fresh-repair `python -m ai_actuarial --help` and `python -m ai_actuarial update --help` passed; the update command still exposes only `--no-search`.
- Fresh-repair `git diff --check origin/main` passed with only normal Windows line-ending warnings.

## Scope and decisions

- Inspected all `scan_page_for_files()` callers. Runtime and both CLI search branches moved to outcomes; `URLCollector.collect()` intentionally retains the compatible list API.
- `crawl_site`, discovery-only `search.py`, and the scheduled collector are same-shaped but have distinct contracts and were not changed. Parent/child orchestration, web listening, BrowserAct, adapter switching, and downstream Markdown/Catalog/Chunk/Embedding/KB/Ready behavior remain out of scope.
- Runtime no longer drops duplicate or off-domain provider rows before acquisition. Every raw result reaches the shared channel; off-domain rows terminate as `filtered/domain` without an HTTP request, while the existing `_dedupe_search_results()` helper contract remains unchanged.
- No sibling checkout, production resource, secret, provider call, commit, push, PR, merge, branch, or worktree lifecycle action was used.
- Graphify was not read, run, or built, and this fresh worker did not create `graphify-out` or any graph files.
- Same-shaped checks were limited to the accepted finding boundaries: page-content content-hash duplicate and direct staged access-wall handling were fixed; `crawl_site`, scheduled `http_403`, global CLI search configuration, parent/child orchestration, and downstream processing remain outside the Round 1 patch.
- Round 2 changed only `ai_actuarial/cli.py`, `ai_actuarial/crawler.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. Prior Round 1 changes in `ai_actuarial/task_runtime.py`, `ai_actuarial/search_acquisition.py`, and `tests/test_task_stop_support.py` were preserved without Round 2 edits.
- Round 3 changed only `ai_actuarial/cli.py`, `ai_actuarial/crawler.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. The existing Round 1/2 changes in `ai_actuarial/task_runtime.py`, `ai_actuarial/search_acquisition.py`, and `tests/test_task_stop_support.py` were preserved without Round 3 edits.
- The fresh repair changed only `ai_actuarial/crawler.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. Existing Issue #263 changes in CLI, Runtime, shared acquisition code, and task-stop tests were not edited.
- Same-shaped lookup review was limited to the linked aggregation loop because that is where prior successful `new_items` can be discarded. Direct-file lookup sites cannot have earlier aggregated items and retain their existing outer outcome/legacy exception behavior; page-content handler failures were already appended to `failures` inside the aggregation path.
- Residual risk is limited to real server MIME-label variation and operating-system/network timing beyond deterministic fixtures. Missing MIME and `application/octet-stream` are deliberately accepted by requirement; no real provider or production resource was used.

## Next step

- Manager/lifecycle worker should repeat the mandatory fresh Codex CLI pre-PR review on the final uncommitted diff before any commit or PR action.

## Fresh pre-PR review 2 repair

### Implementation

- The three linked aggregation lookup catches now cover both local `OSError` and real `sqlite3.Error` failures. `sqlite3.OperationalError` therefore remains inside the mixed-outcome aggregation path, preserving earlier `new_items`, staged cleanup at both post-download lookup sites, and the legacy list caller's rethrow behavior.
- A raw recognized document extension excluded by configured `file_exts` now returns `filtered/extension` before any request. A recognized excluded final extension returns the same rule-only no-op after the final URL is known and before access-wall, body, redirect, or MIME classification.
- Allowed document URLs retain access-wall priority. An allowed `.pdf` redirected to a recognized disabled `.docx` is explicitly `filtered/extension`; an allowed `.pdf` redirected to unknown `.zip` remains `redirect_or_content_type_mismatch/redirect`, and a raw unknown `.zip` successful response remains `no_eligible_file_found/empty`.

### TDD evidence

- Initial test-only run collected 12 focused cases and produced `5 failed, 7 passed, 3 warnings`. The SQLite and raw-extension regressions failed as expected, but the first login fixture used wording outside the crawler's established strong-marker contract.
- After correcting only the login fixture to the existing `Login required` signature, the final pre-production RED run collected the same 12 cases and produced `6 failed, 6 passed, 3 warnings`. Failures were: raw DOCX made the simulated 403 request; `/download` and allowed raw PDF final-DOCX login walls returned `access_blocked` instead of `filtered`; the SQLite mixed lookup returned `items=[]`; and both staged SQLite lookup failures escaped the scoped cleanup/outcome path.
- After the minimal crawler change, the identical focused selection produced `12 passed, 3 warnings`. This includes mixed Runtime/CLI consumption, legacy SQLite rethrow, both staged lookup/cleanup paths, raw/final extension ordering, allowed document access-wall priority, and unknown-extension guards.

### Verification

- Full Issue #263 specialty file: `71 passed, 3 warnings`.
- Crawler/request-policy/allow-pattern/URL-safety/task-stop/scheduled selection: `66 passed, 3 warnings`, including all four scheduled collector tests.
- `python -m compileall -q ai_actuarial tests/test_issue_263_search_acquisition_outcomes.py tests/test_task_stop_support.py` passed.
- `python -m ai_actuarial --help` and `python -m ai_actuarial update --help` passed; the update command still exposes only `--no-search`.
- `git diff --check origin/main` passed with only normal Windows CRLF conversion warnings.
- Warnings were the existing three SWIG dependency deprecations. No test or check failure remains.

### Scope and next step

- This repair edited only `ai_actuarial/crawler.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. The worktree remains the expected 5 modified plus 2 untracked Issue #263 files; no unrelated file appeared.
- No commit, push, PR action, merge, lifecycle-state mutation, `graphify-out` access, sibling-repository inspection, provider call, or production-resource action occurred.
- Next step: repeat a fresh mandatory pre-PR read-only Codex review of the final uncommitted diff before publication work.

## Fresh pre-PR review 3 repair

### Implementation

- Direct and linked staged downloads now inspect `_download_file()`'s final URL immediately after stop handling. A recognized document extension disabled by `file_exts` removes the staged file and terminates as `filtered/extension` with `skipped=1` and `failed=0`, before staged access-wall, body, redirect, or MIME classification.
- Allowed staged PDF access walls retain `access_blocked` priority. A staged final unknown ZIP remains `redirect_or_content_type_mismatch/redirect`, and the existing raw unknown-ZIP no-eligible behavior remains unchanged.
- `_handle_file()` now keeps blob and file persistence in one existing `Storage.transaction()` boundary. If either write fails, the transaction rolls back and only a final path or hard link newly created by that attempt is removed; an existing artifact is preserved.
- Page-content Markdown persistence now uses the same transaction-and-new-path cleanup pattern around its file row INSERT.
- Structured callers still receive `storage_failed/storage` with `downloaded=0`, while the legacy list caller still rethrows the original storage exception.

### TDD evidence

- Focused test-only RED command: `python -m pytest -q tests/test_issue_263_search_acquisition_outcomes.py::test_staged_final_disallowed_extension_is_filtered_before_body_classification tests/test_issue_263_search_acquisition_outcomes.py::test_staged_unknown_final_extension_preserves_redirect_mismatch tests/test_issue_263_search_acquisition_outcomes.py::test_file_persistence_failure_removes_new_artifact_and_database_rows tests/test_issue_263_search_acquisition_outcomes.py::test_page_content_insert_failure_removes_new_markdown_and_database_row`.
- RED result: `7 failed, 1 passed, 3 warnings`. Both direct/linked staged final-DOCX cases were `access_blocked`; `upsert_blob` left a final PDF; `upsert_file` left an orphan blob in structured and legacy modes; both page-content INSERT modes left Markdown. The staged unknown-ZIP guard passed.
- After the crawler-only production repair, the identical focused command passed: `8 passed, 3 warnings`.
- Focused cases use real SQLite-backed `Storage` instances and `sqlite3.OperationalError` at `Storage.upsert_blob()`, `Storage.upsert_file()`, and the page-content INSERT. They assert zero new blob/file rows, no newly created final artifact, preservation of a pre-existing PDF, `downloaded=0`, and legacy exception rethrow.

### Verification

- Full Issue #263 specialty file: `79 passed, 3 warnings`.
- Crawler/request-policy/allow-pattern/URL-safety/task-stop/scheduled selection: `66 passed, 3 warnings`, including all four scheduled collector cases.
- `python -m compileall -q ai_actuarial/crawler.py tests/test_issue_263_search_acquisition_outcomes.py` passed.
- `python -m ai_actuarial --help` and `python -m ai_actuarial update --help` passed; the update command still exposes only `--no-search`.
- `git diff --check origin/main` passed with only the existing Windows CRLF conversion warnings.
- The warnings were the existing three SWIG dependency deprecations. No test or check failure remains.

### Scope and next step

- This repair edited only `ai_actuarial/crawler.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. Existing Issue #263 changes in CLI, Runtime, shared acquisition code, and task-stop tests were preserved.
- The worktree remains the expected five modified plus two untracked Issue #263 files. No unrelated file appeared.
- No commit, push, PR action, merge, lifecycle-state mutation, GitHub access, `graphify-out` access, sibling-repository inspection, primary-checkout access, provider call, or production-resource action occurred.
- Next step: the manager/lifecycle worker should run the next fresh mandatory pre-PR read-only Codex review of the final uncommitted diff.

## Fresh pre-PR review 4 repair

### Implementation and acceptance mapping

- The direct staged-download content-hash lookup now catches both local `OSError` and `sqlite3.Error`. On either failure it removes the newly created `.part`; the legacy list caller rethrows the original exception, while the structured caller receives `storage_failed/storage` with the actual download final URL, `downloaded=0`, and `failed=1`.
- This is the narrow correction for the accepted AC-4/AC-5 finding: the storage failure is no longer represented only by the outer fallback after successful staging, and the structured terminal outcome reconciles with artifact cleanup. Existing duplicate, filter, stop, access-wall, download, and persistence semantics are unchanged.

### TDD evidence

- Exact RED command: `python -m pytest -q tests/test_issue_263_search_acquisition_outcomes.py::test_direct_content_hash_lookup_failure_is_reported_and_cleans_staging`.
- RED result: `4 failed, 3 warnings`. Structured `OSError` and `sqlite3.OperationalError` cases returned `final_url=None` instead of the staged download final URL; both legacy cases rethrew the expected original exception but left the `.part` present. This was the expected production gap.
- After the single scoped crawler lookup change, the identical exact GREEN command passed: `4 passed, 3 warnings`. All four combinations assert structured classification/counters/final URL or legacy rethrow, `.part` cleanup, and no handler call.

### Same-shaped path review

- The three linked aggregation lookup sites already have scoped `(OSError, sqlite3.Error)` catches. The URL lookup occurs before staging; the post-download content-hash and post-handler lookups remove the staged path before reporting/rethrowing.
- The direct post-handler lookup was not changed. It runs only after `_handle_file()` returns `None`; all three normal `None` paths inside that handler already remove the staged file. A lookup exception is still explicit through the structured outer storage-failure outcome or the legacy original exception, so it does not reproduce the accepted artifact-leak condition.
- `_handle_file()` lookup and persistence failures were not changed. They are already caught by the direct/linked callers, which remove any remaining staged path and preserve structured-versus-legacy behavior; transaction rollback plus newly-created final-path cleanup covers persistence writes.
- Page-content lookup/persistence was not changed. It creates no `.part`; new Markdown is removed inside its persistence exception path and the caller reports `storage_failed/storage` or rethrows in legacy mode.
- Other staged paths were not changed. Stop, disabled-extension, access-wall, redirect/content-type mismatch, downloaded-name filtering, linked lookup, and handler-exception paths already remove their staged artifacts. No merely similar code was broadened.

### Verification

- Full Issue #263 specialty file: `83 passed, 3 warnings`.
- Crawler request-policy, allow-pattern, URL-safety, task-stop, and scheduled collector selection: `66 passed, 3 warnings`; the scheduled collector file contributed all four passing cases, preserving `site_results.classification=http_403`.
- `python -m compileall -q ai_actuarial tests/test_issue_263_search_acquisition_outcomes.py tests/test_task_stop_support.py` passed.
- `python -m ai_actuarial --help` and `python -m ai_actuarial update --help` passed; the update command still exposes only `--no-search`.
- `git diff --check origin/main` passed with only the existing Windows LF-to-CRLF conversion warnings.
- All warnings were the existing three SWIG dependency deprecations. No test or check failure remains.

### Scope, risk, and next step

- This repair edited only `ai_actuarial/crawler.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. Existing Issue #263 changes in CLI, Runtime, shared acquisition code, and task-stop tests were preserved.
- Residual risk is limited to the existing best-effort cleanup contract: `_remove_temp_file()` intentionally suppresses an OS error if unlink itself is impossible. Both deterministic lookup exception classes now exercise and pass normal cleanup.
- No commit, push, PR action, merge, lifecycle-state mutation, GitHub access, `graphify-out` access, sibling-repository inspection, primary-checkout access, provider call, secret access, or production-resource action occurred.
- Next step: the manager/lifecycle worker should run the next fresh mandatory pre-PR read-only Codex review of the final uncommitted diff before publication work.

## Fresh pre-PR review 5 repair

### Implementation and acceptance mapping

- The linked-file stopped-result aggregation now preserves the stopped failure row's own `final_url`, falling back to the discovery page final URL only when the row has none. A stop after linked staging validation therefore remains auditable against the linked target instead of being rewritten to the discovery page.
- This is the single scoped correction for the accepted Issue #263 per-result outcome and mixed-result stopped contract. No duplicate, filter, download, storage, persistence, counter, legacy-list, or scheduled-collector behavior changed.

### TDD evidence

- Exact RED command: `python -m pytest -q tests/test_issue_263_search_acquisition_outcomes.py::test_stop_after_linked_staging_validation_cleans_tmp_before_handler`.
- RED result: `1 failed, 3 warnings`. The only failure was `report.outcome["final_url"]`: actual `https://example.com/research`, expected `https://example.com/report.pdf`; the existing disposition, subreason, staging cleanup, and handler-not-called assertions remained satisfied.
- After the one-line crawler fix, the identical exact GREEN command passed: `1 passed, 3 warnings`.

### Verification

- Full Issue #263 specialty file: `83 passed, 3 warnings`.
- Crawler request-policy, allow-pattern, URL-safety, task-stop, and scheduled collector selection: `66 passed, 3 warnings`; all four scheduled collector cases passed.
- `python -m compileall -q ai_actuarial tests/test_issue_263_search_acquisition_outcomes.py tests/test_task_stop_support.py` passed.
- `python -m ai_actuarial --help` and `python -m ai_actuarial update --help` passed; the update command still exposes only `--no-search`.
- `git diff --check origin/main` passed with only the existing Windows LF-to-CRLF conversion warnings.
- All test warnings were the existing three SWIG dependency deprecations. No test or check failure remains.

### Scope, risk, and next step

- This repair edited only `ai_actuarial/crawler.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. Existing Issue #263 changes in CLI, Runtime, shared acquisition code, and task-stop tests were preserved.
- Residual risk is limited to stopped rows that genuinely have no target final URL; the explicit fallback intentionally retains the prior discovery-page value for that case.
- No commit, push, PR action, merge, lifecycle-state mutation, GitHub access, `graphify-out` access, sibling-repository inspection, primary-checkout access, provider call, secret access, or production-resource action occurred.
- Next step: the manager/lifecycle worker should run another fresh mandatory pre-PR read-only Codex review of the final uncommitted diff before any publication action.

## Mandatory pre-PR review 6

- A fresh read-only Codex CLI reviewer inspected the complete five-file `origin/main` diff, both untracked Issue #263 files, and the relevant Crawler, Storage, URLCollector, Runtime, CLI, search-provider, and scheduled-collector contracts.
- Verdict: `PRE_PR_PASS`; no realistically reproducible Issue #263 acceptance-mapped finding remains.
- Reviewer probes passed for Python AST parsing, linked-stop target URL retention/cleanup, direct hash-lookup storage failure classification/cleanup, shared outcome reconciliation, scheduled `http_403`, main/update CLI help, and `git diff --check` (only existing CRLF warnings).
- The reviewer made no file, Git, GitHub, lifecycle-state, sibling-repository, or production change.
- Next step: rerun final validation, then commit, push, and publish the required Draft-to-Ready PR with `Closes #263`.

## Post-Ready remote feedback

- The Copilot review summary and its unresolved inline thread at `ai_actuarial/search_acquisition.py:189` are one finding. It was classified `valid`, with no ambiguous or invalid fetched items; PR top-level comments and Issue comments were empty, and required `python-smoke` was already successful.
- Realistic trigger: both direct and linked `downloaded_new` paths omit `subreason`. The constructor declared `subreason: str | None = None`, and Runtime/CLI contract fixtures represent successful outcomes with `subreason=None`, but membership validation converted that absence to `"other"`. Successful acquisitions therefore logged a fabricated catch-all reason instead of no specific reason, reducing AC-6 audit accuracy.
- The minimal fix preserves absent subreasons as `None` and still maps any unknown non-empty value to the finite `"other"` value. No disposition, counter, error/no-op decision, legacy list behavior, Runtime/CLI flow, or scheduled collector contract changed.
- Exact RED: `python -m pytest -q tests/test_issue_263_search_acquisition_outcomes.py::test_file_like_url_allows_uninformative_mime` — `2 failed, 3 warnings`; both successful direct-download variants returned `"other"` instead of `None`.
- Identical GREEN after the one-line contract fix: `2 passed, 3 warnings`.
- Full Issue #263 specialty file: `83 passed, 3 warnings`.
- Crawler request-policy, allow-pattern, URL-safety, task-stop, and scheduled collector selection: `66 passed, 3 warnings`; all four scheduled cases passed.
- `python -m compileall -q ai_actuarial tests/test_issue_263_search_acquisition_outcomes.py tests/test_task_stop_support.py`, main/update CLI help, and `git diff --check HEAD` passed; diff-check emitted only normal Windows CRLF warnings. A focused contract probe confirmed absent → `None` and unknown non-empty → `"other"`.
- This feedback repair changed only `ai_actuarial/search_acquisition.py`, `tests/test_issue_263_search_acquisition_outcomes.py`, and this status file. No commit, push, PR mutation, review reply/resolve, merge, lifecycle-state mutation, GitHub refetch, sibling/primary checkout access, `graphify-out`, secret, provider, or production action occurred.
- Residual risk is limited to consumers that may have observed the erroneous successful `"other"` value during the short pre-fix branch lifetime; the branch contract and existing nullable fixtures now agree.
- Next step: the manager should inspect this diff, record the single feedback item as a valid change, then commit/push and continue the existing PR lifecycle without a second feedback window.

## Issue #265 implementation worker handoff

### Scope and acceptance mapping

- Added one shared backend indicator contract for nullable 0–100 semantic and keyword relevance plus the stable eight-method retrieval enum and `other` fallback. Invalid, non-numeric, non-finite, and missing semantic inputs stay `None`; legal scores are clamped before rounding.
- All seven Agentic ready-data tools retain their legacy raw `score`, sorting, thresholds, and recall order while adding `keyword_relevance_100` and `retrieval_method`. Each weighted maximum is derived from that tool's existing formula and the unique `_tokens(query)` context; title aliases retain their native 80–100 scale and exact-match 100. Empty queries do not fabricate relevance.
- New vector Chat results and Agentic evidence/citations expose the three shared fields while retaining legacy `similarity_score`/`score`. Historical reads safely normalize existing fields and semantic similarity, leave keyword relevance absent when query/tool context is unavailable, and map unknown sources to `other` without mutating stored messages.
- Citation cards and Retrieved Blocks use the same `RetrievalIndicators` component. It always renders the semantic, keyword, and method badges with `N/100` or an em dash, visible text plus screen-reader labels, wrapping container classes, and non-breaking badge classes. The old user-visible raw `Score` output was removed. English and Chinese labels cover all known methods and `other`; nullable legacy-compatible frontend types were added.

### TDD evidence

- Exact RED command: `python -m pytest -q tests/test_issue_265_retrieval_indicators.py tests/test_chat_react_source.py::test_chat_reuses_wrapping_retrieval_indicators_without_showing_raw_scores; npx tsx client/src/pages/chat/RetrievalIndicators.test.tsx`.
- RED result: Python collection failed with `ModuleNotFoundError: ai_actuarial.retrieval_indicators`; TypeScript failed with `MODULE_NOT_FOUND: ./RetrievalIndicators`. These were the expected missing shared backend/helper and shared frontend component gaps.
- A final adjacent-call self-review found that the Agentic synthesis adapter still relabeled legacy raw keyword `score` as `similarity_score`. The focused RED test failed `1 failed, 3 warnings` with the expected missing raw-score metadata contract. The adapter now retains `score` and passes the three normalized fields without manufacturing semantic similarity; the identical focused test passed `1 passed, 3 warnings`.
- After the scoped implementation and that correction, the final related Python command passed `147 passed, 4 warnings in 19.98s`; the warnings were existing SWIG deprecations and the Starlette `httpx` test-client deprecation.

### Verification

- `python -m pytest --no-cov -q tests/test_issue_265_retrieval_indicators.py tests/agentic_rag/test_ready_data_tools.py tests/agentic_rag/test_planner_agentic_loop.py tests/test_fastapi_agentic_rag_endpoints.py tests/test_fastapi_chat_endpoints.py tests/test_chat_react_source.py` passed: `147 passed, 4 warnings`.
- `npx tsx client/src/pages/chat/RetrievalIndicators.test.tsx` passed.
- `npm run build` passed; Vite emitted only the existing advisory that a generated chunk exceeds 500 kB.
- Focused Ruff syntax/error checks and Python compile checks passed. `git diff --check` passed with only normal Windows LF-to-CRLF notices.
- Browser smoke used `npm run dev -- --host 127.0.0.1 --port 5179` and a temporary local page mounting the production component. At 320, 768, 1024, and 1440 px, document and indicator scroll widths stayed within client widths, the container computed `flex-wrap: wrap`, all badges computed `white-space: nowrap`, accessible names exposed all three metrics, and the adjacent File detail/Preview links remained present. The temporary page was removed, the viewport reset, and the dev server stopped.

### Decisions, risk, and next step

- No formula or data-contract ambiguity was found. The formulas remained tool-specific: summaries `8.75*n+3`, title catalog `7.75*n+4`, title aliases `100`, sections `13*n+3`, formulas `16.5*n+4`, tables `13*n+4`, calculation terms `11.5*n+6`, and relations `2*n+5`, where `n` is the unique current-query token count including the existing CJK bigram behavior.
- Adjacent Chat answer rendering, citation links, File Detail/Preview navigation, historical opening, Agentic endpoint serialization, and planner citation construction were checked through related tests or source-contract assertions. Embedding thresholds, retrieval order, business-tool logic, and unrelated UI were intentionally unchanged.
- Residual risk is limited to browser smoke using a temporary component mount rather than a fully seeded live backend conversation; endpoint/history/link regressions are covered by the related Python and source-policy tests.
- No commit, push, PR, merge, branch deletion, primary-checkout access, sibling-repository access, `graphify-out` access, GitHub mutation, secret access, or production-resource action occurred. Next step: the manager should inspect this uncommitted diff and run the mandatory fresh pre-PR review before publication work.

## Issue #265 managed review Round 1 repair

- Accepted AC-5 finding: the stable backend enum remains `vector`, but its user-facing English and Chinese labels are now `Semantic retrieval` and `语义检索` instead of the internal implementation terms `Vector` and `向量`. No backend mapping, score contract, component structure, or unrelated copy changed.
- Test-first RED: after updating the two expected-label fixtures, `python -m pytest --no-cov -q tests/test_chat_react_source.py::test_chat_reuses_wrapping_retrieval_indicators_without_showing_raw_scores` failed `1 failed` because production i18n still contained the old label. The component test passed independently because its translation function is injected and its updated fixture already rendered the intended label.
- Identical Python source-contract test after the two-line i18n change passed `1 passed`; `npx tsx client/src/pages/chat/RetrievalIndicators.test.tsx` passed.
- Related indicator/source regression passed `59 passed, 3 warnings`; warnings were the existing SWIG dependency deprecations. `npm run build` passed with only the existing Vite generated-chunk-size advisory.
- Round 1 repair touched only `client/src/hooks/use-i18n.ts`, `client/src/pages/chat/RetrievalIndicators.test.tsx`, `tests/test_chat_react_source.py`, and this status file. No commit, push, PR, merge, cleanup, review-state mutation, primary/sibling checkout access, or `graphify-out` access occurred.

## Issue #265 managed review Round 2 repair

- Accepted AC-1/AC-2/AC-5 finding: retrieval-method precedence now remains explicit method first, then a known source mapping, then a recognized tool only when the source is ambiguous `doc_catalog`, unknown, or absent. A `search_summaries()` result sourced only from `sections.jsonl` therefore displays `sections`; `doc_catalog` continues to use the tool to resolve summaries versus titles.
- Test-first RED command: `python -m pytest --no-cov -q tests/test_issue_265_retrieval_indicators.py::test_retrieval_method_mapping_is_stable_and_ambiguous_catalog_is_safe tests/test_issue_265_retrieval_indicators.py::test_explicit_retrieval_method_has_priority_over_source_and_tool tests/agentic_rag/test_ready_data_tools.py::test_search_summaries_labels_section_only_hits_as_section_retrieval`. Result: `2 failed, 15 passed, 3 warnings`; both failures were the expected actual `summaries` versus required `sections`, while explicit-method and catalog-disambiguation guards passed.
- After reordering only the shared helper checks, the identical command passed `17 passed, 3 warnings`.
- Full related Issue #265 selection passed `150 passed, 4 warnings`; warnings were existing SWIG and Starlette dependency deprecations. `npx tsx client/src/pages/chat/RetrievalIndicators.test.tsx` and `npm run build` passed; build emitted only the existing generated-chunk-size advisory.
- Round 2 repair touched only `ai_actuarial/retrieval_indicators.py`, `tests/test_issue_265_retrieval_indicators.py`, `tests/agentic_rag/test_ready_data_tools.py`, and this status file. No enum, formula, sorting, recall, UI, commit, push, PR, merge, cleanup, review-state, primary/sibling checkout, or `graphify-out` change occurred.

## Issue #265 managed review Round 3 repair

- Accepted AC-1/AC-3 finding: `build_retrieval_indicators()` now accepts canonical `semantic_relevance_100`, normalizes it with the existing nullable 0–100 normalizer, and gives any non-`None` canonical input precedence over legacy `similarity_score`. An invalid or NaN canonical value becomes `None` without falling back to raw similarity; only an absent/`None` canonical field derives from similarity.
- Standard Chat serialization, Agentic evidence serialization, historical reference backfill, and Agentic citation construction now pass their canonical semantic field into the shared helper. Method, keyword, formula, sorting, recall, and UI behavior are unchanged.
- Test-first RED command: `python -m pytest --no-cov -q tests/test_issue_265_retrieval_indicators.py::test_shared_builder_prefers_explicit_canonical_semantic_relevance tests/test_issue_265_retrieval_indicators.py::test_standard_chat_serializer_preserves_only_canonical_semantic_relevance tests/test_issue_265_retrieval_indicators.py::test_agentic_serializer_preserves_only_canonical_semantic_relevance tests/test_issue_265_retrieval_indicators.py::test_history_backfill_preserves_only_canonical_semantic_relevance tests/test_issue_265_retrieval_indicators.py::test_agentic_citation_preserves_only_canonical_semantic_relevance`. Result: `5 failed, 3 warnings`; the builder rejected the argument and all four data paths replaced 73 with `None`.
- After the helper and four caller changes, the identical command passed `5 passed, 3 warnings`.
- Full related Issue #265 selection passed `155 passed, 4 warnings`; warnings were existing SWIG and Starlette dependency deprecations. The TS indicator component test and `npm run build` passed; build emitted only the existing generated-chunk-size advisory.
- Round 3 repair touched only `ai_actuarial/retrieval_indicators.py`, `ai_actuarial/agentic_rag/agentic_loop.py`, `ai_actuarial/api/services/chat.py`, `tests/test_issue_265_retrieval_indicators.py`, and this status file. No lifecycle, GitHub, review-state, cleanup, primary/sibling checkout, or `graphify-out` action occurred.

## Issue #265 managed review Round 4 repair

- Accepted AC-1/AC-3 finding: standard Chat serialization and historical reference backfill now infer a missing vector source only when the public shared `normalize_semantic_relevance()` accepts the legacy similarity as finite. NaN and invalid strings produce semantic `None` plus method `other`; legal 0 and 0.9 still infer vector. An explicit `source=similarity` still maps to vector even without a score, and the existing `document_explanation` exception is unchanged.
- Test-first RED command: `python -m pytest --no-cov -q tests/test_issue_265_retrieval_indicators.py::test_standard_chat_infers_vector_only_from_finite_similarity tests/test_issue_265_retrieval_indicators.py::test_history_infers_vector_only_from_finite_similarity tests/test_issue_265_retrieval_indicators.py::test_explicit_similarity_source_maps_to_vector_without_a_score`. Result: `4 failed, 5 passed, 3 warnings`; the four invalid/NaN paths incorrectly returned vector, while all finite and explicit-source guards passed.
- After replacing the two `is not None` checks with the shared normalizer, the identical command passed `9 passed, 3 warnings`.
- Full related Issue #265 selection passed `164 passed, 4 warnings`; warnings were existing SWIG and Starlette dependency deprecations. The TS indicator component test and `npm run build` passed; build emitted only the existing generated-chunk-size advisory.
- Round 4 repair touched only `ai_actuarial/api/services/chat.py`, `tests/test_issue_265_retrieval_indicators.py`, and this status file. No duplicate parsing logic, helper/method/keyword/UI/formula/sorting change, lifecycle/GitHub/review-state action, cleanup, primary/sibling checkout access, or `graphify-out` access occurred.

## Issue #265 mandatory pre-PR gate repair — direct-document indicators

- Accepted AC-1/AC-3 finding: direct `document_content` / `document_sources` chunks carry the compatibility placeholder `similarity_score=1.0` without vector retrieval. Standard Chat serialization and historical read projection now recognize `kb_id=document_explanation` and always publish `semantic_relevance_100=None`, `keyword_relevance_100=None`, and `retrieval_method=other`, while retaining the raw placeholder.
- Historical projection suppresses branch-generated canonical values already stored on a `document_explanation` citation or retrieved block, including stale semantic, keyword, and vector-method fields. Ordinary finite vector and Agentic paths continue through the existing shared builder unchanged. `_prepare_document_source_chunks()` and its `1.0` placeholder were not modified.
- Exact test-first RED command: `python -m pytest --no-cov -q tests/test_issue_265_retrieval_indicators.py::test_direct_document_chunks_do_not_fabricate_retrieval_indicators tests/test_issue_265_retrieval_indicators.py::test_history_suppresses_document_explanation_retrieval_indicators tests/test_issue_265_retrieval_indicators.py::test_chat_vector_and_agentic_serializers_share_indicator_contract`. Result: `3 failed, 1 passed, 3 warnings`. Both direct-document parameters returned semantic `100`; history returned method `vector`; the ordinary finite vector/Agentic guard passed, and the raw direct-document `similarity_score=1.0` assertions passed before the canonical failures.
- After the two narrow projection branches, the identical command passed: `4 passed, 3 warnings`. A same-scope concurrent test covering stale canonical fields on new standard serialization was preserved and also passes in the full selection.
- Full requested Python selection passed: `168 passed, 4 warnings`; warnings were the existing SWIG and Starlette deprecations. `npx tsx client/src/pages/chat/RetrievalIndicators.test.tsx` passed. `npm run build` passed with only the existing generated-chunk-size advisory. `python -m compileall -q ai_actuarial tests/test_issue_265_retrieval_indicators.py`, focused Ruff `E9/F63/F7/F82`, and `git diff --check` passed; diff-check emitted only Windows LF-to-CRLF notices.
- Scoped call-site review confirmed `_serialize_citations()` is used for the standard response and `_backfill_retrieval_indicators()` is applied during conversation detail loading to both citations and retrieved blocks. Agentic evidence/citation serialization, shared normalization, ready-data formulas, sorting, recall, UI, labels, and the direct-document placeholder remain excluded and unchanged by this repair.
- Residual risk is limited to malformed historical direct-document records that lack the stable `kb_id=document_explanation` marker; they cannot be distinguished safely from genuine vector records without expanding the contract. This repair changed only `ai_actuarial/api/services/chat.py`, `tests/test_issue_265_retrieval_indicators.py`, and this status file.
- No commit, push, PR mutation/creation, merge, branch/worktree cleanup, review-state mutation, primary or sibling checkout access, `graphify-out` access, graphify invocation, secret access, provider call, or production-resource action occurred. Next step: the manager/lifecycle worker should inspect the uncommitted diff and continue the mandatory pre-PR flow.

## Issue #265 fresh mandatory pre-PR Codex review

- A new independent Codex CLI review ran read-only against all staged, unstaged, and untracked changes in session `01a04bba-edbb-7870-8379-47f4600e7286` after the direct-document sentinel repair and its regression coverage.
- The review completed with exit code 0 and reported: `No realistically reproducible in-scope defects were identified.` No findings were accepted, rejected, or left ambiguous.
- The review used a read-only sandbox and made no file, Git, GitHub, sibling/primary checkout, `graphify-out`, secret, provider, or production-resource changes. The branch is ready for final local merge-gate validation and publication.

## Issue #265 final local merge-gate validation

- The CI FastAPI smoke selection passed `13 passed, 4 warnings`; warnings were the existing Starlette and SWIG dependency deprecations.
- The CI Agentic eval test passed `31 passed`. The exact Agentic eval CLI smoke returned `3/3` cases passed with evidence hit, citation coverage, and no-evidence refusal rates all `1.0`, and unsupported-answer rate `0.0`.
- These results supplement the post-repair Issue #265 related selection (`168 passed, 4 warnings`), TS component test, Vite production build, Python compile, focused Ruff, browser smoke at 320/768/1024/1440 px, and `git diff --check`, all of which passed.
- No new modified or untracked files appeared during final validation. The only uncommitted files are the expected Issue #265 implementation, tests, and this status update.
