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
