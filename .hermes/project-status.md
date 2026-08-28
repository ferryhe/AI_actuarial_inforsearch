# Project Status — Issue #251 Task-Specific Success Metrics

- Updated: 2026-08-28
- Repository: `AI_actuarial_inforsearch`
- Branch: `codex/issue-251-task-metrics`
- Baseline: `14b7ad19e7d53a90b4e731d4a6bb4ee4ac2df3e9`
- Issue: `#251 fix: show task-type-specific success metrics instead of Downloaded`

## Reproduction and delivery

- Baseline source/runtime reproduction confirmed Markdown, Chunk, Embedding, and unknown terminal tasks were all mislabeled `Downloaded`; acquisition correctly used `Downloaded`.
- A shared `TaskMetrics` resolver now drives active cards, history rows, NativeTasks fallback rows, and the task-log modal.
- Terminal labels are task-specific: acquisition `Downloaded`, Markdown `Converted`, Chunk canonical set/chunk/reuse totals, Embedding canonical expected/ready/generated/reused/invalid-regenerated/failed totals, Catalog scanned/OK/skipped/errors, and generic/local-import `Processed`.
- Active tasks keep live `Processed` progress unless a canonical Chunk/Embedding result is available. Legacy terminal Chunk/Embedding/unknown records use a `Processed` compatibility fallback.
- Existing `items_downloaded` transport fields remain supported; no backend contract or historical record was changed.

## Verification

- Initial #251 TDD reproduction failed as expected, then focused runtime/source coverage passed.
- Managed reviews: three rounds; rounds 1–2 findings were fixed with targeted RED/GREEN coverage, and round 3 passed. Authoritative `review_count=3`; local review is closed.
- Five independent Codex CLI review passes were run across successive fixes; the final pass reported no actionable finding and independently passed #251 tests (`4 passed`), related regression tests (`69 passed`), and the production build (`2137` modules).
- Final manager regression command passed: `33 passed` (three existing SWIG deprecation warnings).
- Runtime TSX metric suite passed.
- Required GitHub `python-smoke` local equivalent passed: FastAPI smoke `13 passed`, agentic eval `31 passed`, agentic CLI `3/3` with JSON/rates valid and zero unsupported outcomes.
- Frontend production build passed (`2137` modules transformed); `git diff --check` passed apart from line-ending warnings.
- In-app Browser `/tasks` smoke passed in English and Chinese for active cards, all terminal task families, history table, and Markdown log modal; acquisition was the only `Downloaded` label and console errors were empty.

## Scope and current state

- Changes are limited to frontend metric rendering, English/Chinese labels, shared task result types, and focused regression tests.
- No backend/task contract, collection semantics, historical data, production operation, secret, or sibling repository was touched.
- Implementation, TDD, managed review, required checks/build, Browser smoke, and the separate pre-PR Codex gate are complete. Draft PR publication and remote lifecycle are next.
