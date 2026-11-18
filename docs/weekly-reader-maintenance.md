# Weekly reader guide maintenance (#434)

The public explanation keeps `status` (`missing`, `complete`, `failed`) and nullable `generation_mode` (`ai`, `empty`, `fallback`, `catalog`). Weeks with no verified new publications use fixed Chinese/English copy without resolving credentials or calling a model. Catalog maintenance uses existing titles and summary excerpts without model calls. Fallback retains its failure audit and displays verified publications. GET endpoints never generate.

The v2 model contract selects exact candidate URLs, source-summary excerpts, and metadata focus values for Chinese and English. The server validates membership, distinct URLs, exact source excerpts and focus values, then supplies titles and complete clickable URLs. Source excerpts retain their original language; introductions and relevance labels are localized. Custom prompts are retained, but must produce this contract. An incompatible custom response visibly falls back. Only an exact saved match of the old default prompt migrates to `weekly-reader-v2`; a later settings save persists that migration.

Candidates come from snapshot members with source evidence for a day-level original publication date inside the UTC week. The public files endpoint returns this list with `published_only=true`, ordered newest first. Its default file list and count describe the full intake archive. Within the eligible candidates, selection considers summary completeness and topic diversity. At most 60 candidates enter selection. Per-item JSON is at most 2,000 characters, material 24,000, user message 26,000, and all messages 32,000. Full URLs are never cut. A conservative UTF-8 byte upper bound reserves output tokens within the configured model context (default 8,000); `model_context_tokens`, `max_context_tokens`, and `model_max_output_tokens` constraints on the Chat route also apply and cannot be expanded by weekly policy. Output defaults to 2,048 tokens and never exceeds 4,096 or a smaller configured model output limit. Budget-limited summaries are not full-text fetches.

The scoped files response includes `backfill_count` for records whose verified publication date falls entirely before the week. Records with unresolved dates or other dates outside the period still count toward intake. The original intake list remains available through the default snapshot files response.

A weekly archive may store verified publisher evidence in `metadata.weekly_publication_date_evidence` under the member URL. The fact includes the current `catalog_date` (explicitly `null` when absent) and the publisher's `source_url`. This keeps the publisher's evidence with the report and the document-bound catalog annotation intact.

Source portals group the latest published archive and the open week's intake by source and UTC collection day. Both views use the same verified source date and UTC week classification. A publication captured on a later day of the same week counts as new in both views.

Invalid JSON, an overlong response, or a timeout gets at most one smaller recovery request, sharing a 120-second deadline with a 60-second maximum per call. SDK retries and the chat client's internal recovery are disabled. Authentication/configuration and unsupported source claims do not retry. The waiting caller enforces the deadline even for an injected generator that ignores its timeout; a late daemon result cannot finalize a record. The production SDK also receives the call timeout. Generation audit data lives in internal `coverage`, outside reader copy.

## Per-snapshot maintenance

Use the intended API instance and its existing operator token. Preview is read-only and returns candidates, exclusion reasons, budgets, and a hash of the snapshot ID/count plus every member URL/first_seen pair:

```powershell
python -m ai_actuarial.cli weekly explanation preview SNAPSHOT_ID --api-url http://127.0.0.1:5000 --json
python -m ai_actuarial.cli weekly explanation regenerate SNAPSHOT_ID --dry-run --api-url http://127.0.0.1:5000 --json
```

An explicit regeneration updates only the explanation. Its response contains before/after membership hashes and the resulting mode/status:

```powershell
python -m ai_actuarial.cli weekly explanation regenerate SNAPSHOT_ID --api-url http://127.0.0.1:5000 --json
```

Repeated normal generation reuses the current fingerprint, including an existing fallback; `retry` explicitly retries a failed result. A changed prompt has a new fingerprint. Claims provide single-flight across processes. A failed regeneration preserves the previous successful explanation and stores the failed attempt in its internal audit. Snapshot creation, dates, members and counts are never changed by these commands.

Historical targets are enumerated in `tests/fixtures/weekly_reader_history.json`:

- Overseas: `weekly-9144d5e429064131aaa1e00f6ff94305` (0), `weekly-c493815300694d9dac4417590256b973` (216).
- Domestic: `weekly-93686d5e7907465fb3d801bf6fac8948` (0), `weekly-7b9584a8b1084c54aad977ed437d362a` (99), `weekly-4b2f4e0b63b9441faf2b5fe42d4119cb` (5).

These IDs in tests use synthetic content, not copied production rows. No production replay is performed by this change. To reproduce the isolated evidence using this repository's disposable PostgreSQL fixture:

```powershell
$env:POSTGRES_TEST_URL='postgresql://YOUR_DISPOSABLE_TEST_DATABASE'
$env:ISSUE434_EVIDENCE_DIR='C:/absolute/path/to/evidence'
python -m pytest -q --no-cov tests/test_issue_434_weekly_postgres.py
```

The fixture writes `historical-isolated-replay.json`: dry-run selection, execution receipts, before/after hashes, synthetic old/new bilingual copy, and generation audit data. It explicitly labels `fixture_only: true` and `production_replayed: false`. Production maintenance requires separate deployment authorization and actual per-environment readback; this fixture is not that evidence.

## Validation and rollout

Run the three official weekly Python suites plus the reader/claim suites, the two weekly Vitest files, typecheck and build. The browser fixture can be checked with `npm run dev -- --host 127.0.0.1 --port 5434 --strictPort` followed by `node client/src/lib/issue434-weekly-reader.browser-smoke.mjs`; it mocks HTTP responses and checks both languages on home/detail for empty, AI and fallback modes. Set `CHROME_PATH` if Chrome is installed elsewhere, and `REPORT_DIR` to save screenshots.

Mode and audit use the existing coverage JSON. Deploy backend and frontend together, preview the intended snapshots, then perform authorized regeneration. Rollback uses the prior code and saved configuration and preserves the intake archive. Public reads use the current verified publications to render a replacement when a stored guide predates publication filtering or its eligible list has changed.
