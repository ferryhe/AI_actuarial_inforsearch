# Assistant UAT and rollout gates

[Issue #480](https://github.com/ferryhe/AI_actuarial_inforsearch/issues/480) uses the frozen [matrix](../tests/fixtures/assistant_uat_questions.json). It contains 64 independent questions, including 24 prompt-held-out rewrites, and 12 multi-turn tasks. The earlier help fixture remains a separate regression suite.

## Freeze before the first model call

1. Record the clean full Git SHA and SHA-256 of this runbook, the matrix, and the effective UAT harness. Record the environment and commands, UTC start, evaluator, allowed provider spend, and two approved snapshot IDs. Check held-out wording against the served instructions and examples, including active published skill artifacts. Keep the matrix, reference answers and evaluator out of product prompts and KB content.
2. For each site, bind the logical targets to the canonical catalog URL, actual file ID, permitted KB ID, section, and Ready publication or Standard index version. Bind guide targets to their locale, section, version and hash. Save expected rows, UTC query time and window boundaries for relative periods. Take the expected facts and identifiers from the permitted sources.
3. Create the roster of every site and case or task/turn ID before execution. Keep the first execution and each evaluator replay of a question or task turn as separate records. Any change to the candidate, harness, content, rubric or gate needs a new dated run and hash. Preserve earlier rosters and attempts.

The official Spring 2026 report supplies the anchor findings. The publisher page lists October 29, 2026. Both site records have a null stored publication date, which stays unknown when assessing the assistant. Keep these dates separate from the spring survey wave and system dates. The year-qualified URL in the publisher's Suggested Citation returned HTTP 404 and is kept in the matrix as verification evidence. A catalog alias must be reachable and bind to the same verified report and section in the snapshot. [SOA Spring 2026 report](https://www.soa.org/resources/research-reports/soa-member-ai-survey/)

Pages 4–5 of the March bulletin contain the invitation to participate. The prior beta hostname failed DNS resolution in the verification environment and is kept in the matrix as verification evidence. The Summer 2025 report is a separate comparison document. [March bulletin PDF](https://www.soa.org/globalassets/assets/files/resources/research-report/2026/2026-03-ait170-ai-bulletin.pdf), [Summer 2025 report](https://www.soa.org/resources/research-reports/2025/ai-member-survey-summer-2025/)

## Isolated preflight

Require an explicit config and approved binding for each site before importing app settings or connecting. Stop on any missing or unknown prerequisite.

- Restore each approved snapshot to an owned PostgreSQL 16 instance and a separate data copy. Use literal loopback database and HTTP addresses and dedicated ports. Verify the instance, database name and owner against the restore record. Reject a forwarded production or shared local database. Verify the effective config, data, files, logs, KB index and artifact paths resolve under the owned run root, including absolute overrides and symlinks. Do not mount production volumes.
- Start with a clean environment. Set `AI_ACTUARIAL_IGNORE_DOTENV=1` before import, set explicit `CONFIG_PATH`, and set the disposable database through the configured `database.url_env` (default `DATABASE_URL`). Confirm effective `DATA_DIR` / `paths.data` and nonproduction server mode. Use only approved injected or cloned encrypted credentials. Leave bootstrap-admin variables unset. Do not dump environment, DSNs, credentials, cookies or authorization headers.
- Confirm China resolves DeepSeek and overseas resolves the existing, explicitly approved Chat provider, model and HTTPS host. Confirm effective Chat and required embedding bindings, including the non-secret credential source. Allow only those approved outbound provider origins. Reject unknown or production application endpoints, unknown provider endpoints and outbound redirects. Keep both configs and their evidence separate.
- Remove default and site schedule intervals and disable all cloned `scheduled_tasks`. The factory still starts a daemon for pipeline-baton and Ready Data polling. In the isolated launcher only, replace `NativeTaskRuntime.init_scheduler` with a no-op before calling `ai_actuarial.api.app.create_app()` and keep that seam for the process lifetime. Verify zero scheduled jobs, no scheduler loop, and no task starts. The unwrapped server entry point starts those jobs.
- Use the normal factory, route, identity, provider binding and SDK. Explicitly enable Assistant and set allowed public/staff KBs. Feedback uses its own flag and a disposable site key. Allocate enough allowance with disposable principals; preserve identity within a task unless the scenario changes it. Use an exhausted disposable principal for quota tests. Production quota, business dates, KB/skill releases and feedback are outside this run.
- Verify health, capabilities, artifact integrity and each scenario's seed without model calls. Check route and usage capture with a stub before allowing any outbound model call. Missing approval, snapshot, credential, telemetry or scheduler proof means `ENVIRONMENT_BLOCKED`.

### Scenario bindings

The baseline needs the Spring findings and 2025 comparison bodies, the March announcement as a separate catalog item, public/staff/unlisted controls, a complete latest weekly period with additions, and a historical published period. Create variants only on disposable copies and record each seed or restore command and evidence checksum. Reset to the declared scenario before each independent question or task. Use a disposable registered identity by default, with explicit identities for access scenarios.

| Scenario | Preflight proof |
| --- | --- |
| `published_weekly`, `no_weekly_snapshot`, `empty_weekly_snapshot` | Match published periods and member lists. The no-snapshot state has no complete published period. The empty state has a complete latest period with zero members and an older populated period. |
| `distinct_dates` | Publication, first collection and KB-added dates have distinct values. Record each and the absence of revision lineage. |
| `summary_only`, `missing_body`, `incomplete_body`, `index_mismatch` | Retain permitted catalog records. Summary-only uses the long-term care fairness listing in standalone cases and SOA in T06. Missing body has no readable evidence. Incomplete body lacks Key Findings. Mismatch has no usable Ready or compatible Standard serving index. |
| `soft_stale`, `hard_stale_same_kb_standard` | Record the usable earlier Ready publication and stale flag, or the rejected Ready publication and active same-KB Standard index. |
| `anonymous_staff`, `registered_staff`, `operator_staff`, `admin_staff`, `admin_unlisted`, `empty_scope`, `staff_revocation` | Record server-derived identity, scopes, allowlists and exact control file/KB IDs. Seed a unique staff body marker and a file outside the allowlists. Record the actual role change in the revocation task. |
| `exhausted_quota` | Seed an exhausted disposable principal for the current UTC day. Verify zero provider calls. |
| `provider_failure` | Use a controlled transport failure in the deterministic lane. Preserve the injected error and actual bounded adapter attempts. |
| `feedback` | Begin with zero matching rows. Verify unchanged count after draft/cancel, and one edited row and server-issued receipt after explicit confirmation. |

### Minimum approved data for real-provider UAT

For each site, supply a sanitized snapshot or an equivalent approved export with its restore ID and hashes. Include the three SOA catalog records, exact readable Spring and Summer body sections and KB membership, the small permitted source directory and first-seen sample (including its UTC windows), two published weekly periods and their exact members, and the served KB indexes, skill artifacts and guide versions. Supply only data cleared for the corresponding provider. Synthetic staff/unlisted markers, test identities and permissions, stale/unavailable variants, quota state and feedback belong in the isolated copy. A full production dump, production identities and unrelated documents are unnecessary.

The site owner must confirm the provider origins, functioning Chat and any needed embedding credential bindings, and the allowed test spend separately. Isolated evidence must preserve those effective bindings and the served data and artifact identity.

## Run and score

Run the deterministic cases against an owned, loopback-only `POSTGRES_TEST_URL`. The matrix contract tests work without PostgreSQL. The frontend tests use a stub transport.

```text
python -m pytest --no-cov tests/test_assistant_uat_matrix.py tests/test_assistant_help.py tests/test_assistant_knowledge.py tests/test_document_research.py tests/test_assistant_agent_runtime.py tests/test_fastapi_assistant_endpoints.py tests/test_assistant_feature_matrix.py tests/test_fastapi_feedback_endpoints.py
npx vitest run --config vitest.config.ts client/src/features/assistant client/src/features/feedback
```

After preflight passes, send the frozen question as-is to `POST /api/assistant/v1/query` with the matrix language as `locale`. Start independent questions with empty context. For tasks, use the normal browser flow or record the equivalent payload. Carry the verified `selected_target` or actual `opened_file_url` and last three questions as the browser does. Clear them after Clear conversation and when identity changes, except for explicit stale-hint replays.

A user-requested retry in the script is a regular task turn. T12 has two first executions (turn 1, attempt 1 and turn 2, attempt 1). Run the guide and canceled feedback actions between them, retain both quota rejections, and verify zero provider calls. The fixture's `user_requested_retry` flag describes the turn wording. For an evaluator replay, restore the same question or turn's original preconditions and history and append the next attempt under that ID (for example, turn 2, attempt 2). Keep attempt 1 and use it for scoring.

Verify the actual `Outcome.runtime.trace` at the Host boundary. Listed tools are alternatives within one expectation. Every `also_expect` must independently match. Discovery may precede a valid final route. An empty tool list requires no evidence-producing route and zero provider calls where specified. Compare target, citations, actions and material claims against the source. Score the answer language, required facts, forbidden claims and task completion. An expected unavailable or denied response passes when it matches its seeded state.

In a real browser on both isolated sites, record the two exact anchor prompts, working citations/actions, older-week selection, file opening, and Clear across navigation. Exercise feedback cancel/edit/confirm, desktop and phone-size layouts, long input and answer scroll, and keyboard access. Keep redacted screenshots or video and matching network evidence. Physical iOS is tracked in [#489](https://github.com/ferryhe/AI_actuarial_inforsearch/issues/489) and remains `NOT_RUN`.

| Gate | Passing evidence per site |
| --- | --- |
| Anchors | 100% on the first attempt for every `critical` question and held-out anchor variants ZH05, ZH06, EN05 and EN06. SOA needs the verified Key Findings body. Weekly needs a working `/weekly` and steps the browser can follow. |
| Deterministic contracts | 100% for source IDs and membership, permission and revocation, dates, real citations/actions and feedback confirmation. Any failure blocks acceptance. |
| Held-out | At least 22 of 24 first answers get both route and target right (at least 90%). Report grounded facts, language and completion scores separately. |
| Multi-turn | At least 11 of 12 tasks completed (at least 90%) using first attempts. Every turn and required browser action in a completed task meets its rubric, including any expected safe denial. |
| Evidence | Publish every case by site and locale. A `NOT_RUN` or `ENVIRONMENT_BLOCKED` case needed by a gate keeps it open even if the arithmetic threshold is reached. Injected fault cases stay in the deterministic lane. |

Use `PASS`, `FAIL` for an executed case that missed the rubric, `NOT_RUN` for a planned case left unexecuted, and `ENVIRONMENT_BLOCKED` for a missing or unverified prerequisite. Give each non-pass a reason. An HTTP 200, available status or citation alone earns no pass. Human review checks every anchor, contract violation and failed case, and samples successful results in both languages. A model judge may assist with rubric review.

## Evidence required for a release decision

Use an append-only JSONL attempt ledger and link each grade to its source proof and sanitized response.

| Record | Required fields |
| --- | --- |
| Run identity | Site, lane (stub/isolated real/production observation/device), run ID, clean full code SHA, package/build/image IDs, frontend bundle hash, config hash, matrix and harness hashes, data snapshot and clock, and effective flags/allowlists. Capture `/api/health` and authenticated `/api/health/detailed` and corroborate full build identity from the builder. |
| Runtime and data | Feature `assistant`, public schema version, runtime contract and budgets, enabled skill versions, active/previous release IDs, slot revisions, source refs and artifact digests. For each served KB include Ready publication/manifest hash or Standard index version/hash, exact file/section IDs and stale status. Record help version/hash and weekly snapshot ID as applicable. |
| Provider | Actual Chat and embedding provider, model, host and non-secret credential-binding source per site. Capture provider-returned model IDs. |
| Attempt | Question or task/turn ID, attempt number within that question or turn (1 for first execution, 2+ for evaluator replays), user-requested retry marker if applicable, UTC start, end-to-end milliseconds, HTTP status and product error code, sanitized payload and response path, tool trace, target, source and action proof, and each rubric grade and status reason. Include generation, routing, answer and embedding counters, plus every physical provider call, including verifier, recovery, embedding probe and retries. |
| Physical usage | Correlate sanitized provider request IDs, operation, per-call latency and outcome, input/output and applicable cached/reasoning tokens, billed amount or a labeled estimate from measured usage and dated applicable rates. Verify zero with evidence of no calls. Missing required usage, pricing or call attribution blocks the gate. Report site totals and p50/p95 separately by lane. |

Observe the normal Host outcome and SDK call/response without replacing the provider. Reconcile observations with the response counters. The public response exposes counters and evidence IDs; capture full trace and usage separately. Stub results, estimates of token counts, an unapproved fallback and earlier candidate runs do not satisfy real-provider acceptance.

## Staged rollout and rollback

1. Keep production untouched until separately authorized. A candidate needs both sites' frozen gates, independent review, and required CI on its SHA (`dead-code-files`, `dead-code-symbols`, `python-smoke`, `quality-gate`, `office-conversion-smoke`, `frontend-check`). Rehearse rollback in isolation and capture the previous artifact/slot, allowlists, configuration and frontend/backend identities. Record the rollout and rollback owners, observation thresholds, change window, and approved traffic and spend caps for each site before rollout.
2. With authorization, start on one site with the smallest approved internal cohort. If cohort isolation cannot be verified, stop before enabling Assistant. Verify Help/Weekly, catalog, report reading, access denial and manual feedback separately using authorized actions. Observe for at least 24 hours with a pre-rollout baseline and sample counts for traffic, errors, p95 latency, quota denials, provider usage and spend. Require the anchor and contract probes to remain green and metrics to stay within the preapproved bounds. Missing evidence, insufficient samples or an unknown owner blocks expansion. Apply the same gate to the second site before expanding.
3. Stop expansion on an access leak, wrong anchor source/action, unauthorized feedback write, unexpected provider, or breach of agreed error, latency or spend bounds. The rollback owner disables Assistant using its effective feature setting and checks `/api/support/capabilities` and the versioned route. Preserve the approved independent feedback setting. If needed, use the existing compare-and-set skill rollback to the pinned previous release or redeploy the pinned previous artifacts. Verify build IDs, allowlists, feature exposure, previous behavior and feedback receipt safety. Record UTC times, trigger, rollback action and probe evidence before a new attempt.

Report deterministic CI, isolated real UAT, production observation and physical device results in separate rows. Production observation and physical iOS stay `NOT_RUN` until separately evidenced. Issue closure or a candidate build alone cannot complete the assistant batch.
