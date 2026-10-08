# Issue #407: KB and category loading evidence

## Change and production evidence

The KB administrator list keeps its existing aggregate and fallback logic. It now pins the coverage query to the existing `idx_global_chunks_stats_metadata` and `idx_chunk_embeddings_stats_metadata` indexes when those indexes are present. The check reads `sqlite_schema`; it creates no index and remains compatible with older read-only databases that lack either index. The category page loads `/api/categories?mode=used` independently, then requests category mapping with `include_diagnostics=false` and Chat readiness only for roles that can use Ask AI. The KB management page renders its primary list error with a retry action instead of presenting a failed request as an empty list.

The production diagnosis below was supplied by the user from a read-only profile; this worker did not run it against production. The two full admin KB-list requests took 57.29 s and 46.62 s. `_prepare_coverage` took 57.07 s and 46.41 s. The profile identified SQLite choosing an ordinary index and visiting vector-table data pages even though covering metadata indexes already existed. With the existing indexes pinned and SQL/result logic unchanged, the user measured 0.54–0.64 s for the full service and 0.35–0.45 s for the coverage SQL. No production writes, migrations, deployment, or configuration changes were made here.

Before the UI change, the first live admin category-page observation still showed the loading skeleton at 24.781 s; cards were visible by 83.087 s. On a repeat visit, the skeleton was still visible at 23.081 s; cards were visible by 56.975 s. These interval-censored page observations are not endpoint timings or production TTFB measurements. No post-change production result is available because this branch has not been deployed.

## Local backend profile

The automated profile seeds a local SQLite fixture with 8,704 chunks, 3,072-dimensional embedding metadata, and two KBs sharing the same chunk set. It runs both plans against the same database and asserts equality of the complete list payload. The separate coverage regression checks ready embeddings, wrong identity, invalid bindings, `EXPLAIN QUERY PLAN` covering-index selection, and fallback after the existing indexes are absent.

One run on this Windows worktree reported:

| Plan | First call | Repeat call | SELECT statements | JSON payload |
| --- | ---: | ---: | ---: | ---: |
| Existing covering indexes pinned | 52.2 ms | 44.4 ms | 38 / 38 | 8,957 bytes |
| Index hints disabled | 182.0 ms | 170.7 ms | 37 / 37 | 8,957 bytes |

The extra SELECT for the hinted plan checks index names in `sqlite_schema`. These are sequential local calls without an OS cache flush; the numbers are a reproducible fixture comparison, not production cold-cache measurements or an SLO. The local fixture demonstrates the query-plan effect but does not reproduce the production multi-second delay.

Run the focused profile and equivalence tests with:

```powershell
python -m pytest tests/test_issue_256_lightweight_list_apis.py -q -s --no-cov
```

## Chromium UI fixture smoke

`client/src/pages/Issue407KbCategoryLoading.browser-smoke.mjs` serves the locally built UI bundle through Playwright routes and intercepts the API with deterministic role fixtures. It uses installed Chrome/Chromium through `playwright-core`; no external service or account is used. The fixture has 16 categories and delays the registered user's KB mapping by 1.3 seconds and Chat readiness by 1.6 seconds. It measures category-route TTFB, total API fixture duration, API JSON bytes, API request count, and time until the category grid is visible. It also checks guest request shape, local search and Database category filtering, category-mapping failure/retry, and KB-list failure/retry to a valid empty response.

Run it after building the client:

```powershell
npm run build
node client/src/pages/Issue407KbCategoryLoading.browser-smoke.mjs
```

The captured run used the local 900 ms category-grid and 300 ms category-response budgets (test budgets only; not a P95 or SLO):

| Role | Load | Categories | API requests | Category TTFB | API duration | API JSON bytes | Grid visible |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Guest | First navigation | 16 | 2 | 73 ms | 102 ms | 624 | 357 ms |
| Guest | Reload | 16 | 2 | 69 ms | 90 ms | 624 | 249 ms |
| Registered | First navigation | 16 | 4 | 61 ms | 1,636 ms | 911 | 310 ms |
| Registered | Reload | 16 | 4 | 63 ms | 1,634 ms | 911 | 237 ms |
| Admin | First navigation | 16 | 4 | 73 ms | 1,135 ms | 939 | 320 ms |
| Admin | Reload | 16 | 4 | 73 ms | 1,137 ms | 939 | 263 ms |

The route-level TTFB includes the fixture's 60 ms category delay; API durations include deliberately delayed auxiliary calls. Byte counts cover serialized API JSON bodies, not browser assets or HTTP headers. The legacy page waited for the category and auxiliary requests together; in this controlled registered fixture that dependency would keep the grid waiting for the 1.6 s readiness response. The measured post-change grid appeared in 237–310 ms while those fixture requests remained pending. This before value is derived from the old `Promise.all` dependency and injected delay; we did not run the old build in Chromium against this fixture.

## Deployment boundary

The production timing improvement still needs confirmation after deployment against production data. Verify full list payload equivalence and the expected covering-index plan on the deployed database, then collect fresh admin-list and category-page timing. The local data above does not establish a production percentile or service-level target.
