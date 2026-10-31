# Publisher source identities

The Hub PostgreSQL database is the maintenance authority. `canonical_sources`
holds stable keys, Chinese/English names, status and official-site evidence;
`source_aliases` holds exact names/hostnames and explicit ambiguity. App
PostgreSQL databases hold complete versioned replicas. No cross-machine DB
service, new credential, signing system or management UI is introduced.

`config/source_registry_seed.json` is a reviewed **initial import**, not the
runtime authority. Publish it explicitly into Hub PG. Subsequent edits use the
same reviewed export/import contract with an increasing `registry_version`.
Every export and acknowledgement contains the canonical JSON SHA-256. An equal
revision with a different hash, or an older revision, is rejected. Preserve
historical sources and alias spellings; mark a source retired or an alias
ambiguous instead of dropping it. Zero current articles never deletes a master
source. An unchanged dictionary retains its revision.

## Attribution and reader contract

`files.source_site`, discovery URLs, raw manifests and immutable Hub observations
remain raw provenance. `files.source_key` is only an import cache, never read
or filter authority. Both Hub and app `source_projection` contain only reviewed
exact article overrides. Every app read/count/filter and Hub list/exact read uses
that override, then the current verified DB aliases, then `pending`. An alias
addition, retarget or ambiguity immediately changes existing automatic articles
without article replay or cache backfill. A display-name edit immediately uses
the current canonical name. Automatic resolution never creates an override.
The list/detail/KB APIs retain raw `source_site` and separately return
`source_key`, `source_name_zh` and `source_name_en`. Reader pages display the
selected language's name. Task types, collector types, conversion engines,
model providers and other operational input labels keep their own semantics.

Resolution uses an exact URL + original raw SHA overlay first, then an exact
verified original URL hostname. An official host identifies the publication
**website**, not a claim that the association authored every hosted paper.
Discovery-page membership does not identify an external publisher. Shared CDN,
external/reprint URLs and unverified hosts are `pending`; no suffix/wildcard
hostname matching is used. For non-web/local inputs, only an exact verified raw
name can resolve. Arbitrary original metadata/body evidence requires a reviewed
exact article correction; no text classifier guesses institutions.

The seed contains official name/host evidence. `task`, `cia` and `cca` are
ambiguous historical shorthand. In particular TASK is **The Actuarial Society of
Kenya**; the official Kenya hostname or exact article evidence resolves it, but
the arbitrary raw string `task` does not. IAJ/AIJ historical names require the
same URL/article evidence. SOA sections share `soa` only when the original URL
host or reviewed exact article proves the publication site.

`/api/sources` returns stable keys in `sources` and bilingual positive-count
objects in `source_options`. Counts and exact filtering use the article list's
visibility condition: nonempty `local_path` and `deleted_at IS NULL`. Deleted,
hidden and article-free canonical sources stay out of the dropdown. Pending is
a valid option when pending visible articles exist. CAS never matches CASA.
Weekly/deep links and interpretation routes already carry the article list's
`source` parameter and use this same shared filter.

Old bookmarks resolve by exact normalized key, verified name alias, or exact
Chinese/English canonical name (trim + lowercase, v1). Unknown/ambiguous values
have a deterministic **zero-match** result; they never become substring queries
or expand into every pending article. In particular a raw collection label does
not become an alias of `pending`.

## Explicit rollout (not executed in production for Issue #435)

Use existing DB environment variables and the existing SSH target configuration.
Do not put credentials into command arguments or reports. The examples assume
the Hub's dedicated environment is configured. App schema v4 and Hub schema v4
must first be reviewed/applied through their existing migration/deployment tools;
all old migration files remain unchanged. Legacy SQLite v16 stays frozen for
historical import/validation only.

```powershell
python -m ai_actuarial.source_registry_cli publish --hub --manifest config/source_registry_seed.json --json
python -m ai_actuarial.source_registry_cli publish --hub --manifest config/source_registry_seed.json --apply --json
python -m ai_actuarial.source_registry_cli export --hub --json
python -m ai_actuarial.source_registry_cli sync --hub --config PATH_TO_EXISTING_LOCAL_FLOW_CONFIG --json
python -m ai_actuarial.source_registry_cli sync --hub --config PATH_TO_EXISTING_LOCAL_FLOW_CONFIG --apply --json
python -m ai_actuarial.source_registry_cli inventory --hub --json
python -m ai_actuarial.source_registry_cli inventory --json
```

`sync` streams one narrow registry operation through the existing SSH/JSON target
worker. The receiver checks the existing native target KB/profile identity and
returns target, revision, hash, row counts and receipt ID. Each target receipt must match the requested revision/hash. Both targets are
attempted independently; failures remain pending and successful receipts remain
in Hub for diagnosis/retry. Partial/failed synchronization returns nonzero. The final
report distinguishes the requested revision from the current Hub revision. If
Hub advances during synchronization, status is `hub_advanced` and CLI exits 2;
it does not claim both replicas hold the latest dictionary. A dry-run reads profiles/dictionary without schema creation
or writes. Deploy matching app code/migrations before using the streamed worker;
it imports the shared source resolver from that release.

Published Hub article projections carry the registry revision/hash and nullable
`source_override_key` in their metadata fingerprint and acknowledgement. These
are derived transport metadata; historical content signatures, annotation
digests and dictionary hashes do not change. A target without a successful
current-Hub-revision receipt remains pending; another acknowledged target can
proceed independently. A mismatched dictionary is rejected before article writes.
The per-target ACK/Ready and retry contracts remain independent.

The marker has three states:

| Article field | Meaning | Target behavior |
| --- | --- | --- |
| Missing | Legacy message without override authority | Preserve existing overlays; resolve using the current target dictionary. A versioned message missing this field requires a fresh Hub read. |
| Present `null` | Hub currently has no exact override | Require no target overlay and matching current automatic resolution. Report conflict if a target overlay exists; never delete it. |
| Present canonical key, including `pending` | Hub expects an exact override | Require the same target overlay backed by its explicit target correction receipt; otherwise report conflict/pending. |

Article delivery/replay **never creates, replaces or deletes an exact overlay**.
A nonnull marker requires a separately reviewed `correct` on each target's exact
URL/raw-SHA identity, followed by article delivery. Store that target receipt and
include the Hub apply receipt ID as the correction record's `upstream_receipt_id`
for the audit trail. An ACK includes `source_correction_receipt_id`; it proves the
accepted target state, not cross-machine transactionality. If a target has no
exact file identity yet, it remains pending until that identity exists through
an already permitted import path; a marker does not extend URL/publishing rules.

Hub rollback changes only Hub state. Explicitly rollback each accepted target
using **that target's own original correction receipt**. Confirm each returned
receipt/readback separately before claiming all endpoints converged. Hub completion
alone does not mean either target is complete. A missing target correct/rollback
receipt keeps that target `pending` and the aggregate `not_converged`; a failed
endpoint stays independently pending while a successful endpoint can ACK/Ready.
A target local correction is never cleared by an automatic or legacy message.
After target rollback, replaying the old exact marker fails the target state
check and cannot recreate the revoked overlay, even at the same dictionary
revision. There is no automatic rollback cascade or new synchronization ledger.

## Inventory and exact correction

Inventory distinguishes raw Hub observations from app articles. Its per-raw
groups include visible/hidden counts, canonical keys, representative identities,
disposition and the dictionary revision/hash. Never compare Hub observation
counts with article totals or equalize independent environments by copying or
deleting articles. A pre-v4 production snapshot has no dictionary version: record
its raw counts and unresolved attribution separately until the reviewed rollout.

`plan --json` reports `cache_differences` and unresolved articles without writes.
Its executable `records` list is empty: automatic alias/cache differences are
not evidence for a manual override. Exact corrections need separately reviewed
article evidence. A plan records its dictionary revision/hash; stale reviewed
manifests are rejected.

```powershell
python -m ai_actuarial.source_registry_cli plan --json
python -m ai_actuarial.source_registry_cli plan --hub --json
```

A reviewed correction file contains `records`:

```json
{
  "records": [{
    "url": "https://publisher.example/exact-original.pdf",
    "raw_sha256": "REPLACE_WITH_THE_EXACT_64_CHARACTER_ORIGINAL_SHA256",
    "raw_source_site": "local_docling",
    "old_source_key": "pending",
    "new_source_key": "cas",
    "reason": "Exact original identifies the publisher",
    "evidence": ["Reviewed original cover/page and official source URL"]
  }]
}
```

```powershell
python -m ai_actuarial.source_registry_cli correct --manifest reviewed-corrections.json --json
# Save the dry-run JSON as reviewed-dry-run.json; it contains request_id + old_override.
python -m ai_actuarial.source_registry_cli correct --manifest reviewed-dry-run.json --apply --json
python -m ai_actuarial.source_registry_cli rollback --receipt ORIGINAL_RECEIPT_ID --json
python -m ai_actuarial.source_registry_cli rollback --receipt ORIGINAL_RECEIPT_ID --apply --json
```

Use `--hub` for Hub overrides; default mode applies to the configured app DB.
For a Hub row with no overlay, expected `old_source_key` is JSON `null`; for app
rows it is the **current effective key**, never the cache. Exact URL/raw SHA and
raw source value are checked under the existing registry/file locks. Missing
identities skip; changed raw values, expected keys or overlay state conflict.
An explicit `pending` is a real manual override; setting CAS when the automatic
alias already yields CAS still creates a manual overlay and receipt.

Every non-rollback apply, through either CLI or `correct_sources`, requires the
saved dry-run `request_id` and every record's complete `old_override` snapshot:
`exists`, `source_key` and `correction_receipt_id`. Missing/malformed fields or a
missing ID are rejected before writes. The complete current overlay state must
still match that snapshot, including its pointer even when the effective key is
unchanged; otherwise the row conflicts and is not changed. CLI conflicts exit 2.
The original records-only manifest with `--apply` is rejected, including when an
ID is supplied just for apply. Save/review the dry-run JSON, then apply that same
JSON. Rollback continues to use the original apply receipt's after-state CAS and
does not require a non-rollback preview.

Dry-run also records `reconfirm_same_key` in `request_body`: false when the caller
did not explicitly supply an ID, true when the operator supplied a new ID during
dry-run. Apply preserves that reviewed intent. The API accepts the saved
request body's records, `request_id` and `reconfirm_same_key`; it does not create
an apply ID or silently substitute a missing snapshot. A repeated identical
ID/body is unchanged only while its recorded after state and pointer still
match; reusing an ID with a different body is rejected, and a later correction
gives a conflict. A normal preview/apply leaves an existing same-key overlay
unchanged. To deliberately reconfirm it, provide a new `--request-id ID` **during
dry-run**, save that preview and apply it; the new receipt owns the overlay and
an older rollback cannot remove it. An apply-time ID cannot replace the saved
preview ID. Preview JSON remains reviewable/editable input; no preview checksum,
signature or additional trust protocol is introduced. Safety comes from the
current database identity/overlay/pointer comparison.

Receipts use `overlay_state_version: 2` and record full before/after overlay
presence, key and `correction_receipt_id`. The projection pointer references the
existing receipt table. Rollback compares the exact identity, raw value and the
current after pointer/presence/key, then restores the prior state including its
pointer. If no overlay existed before, deleting the override returns the article
to the **current alias**, not an old cached result. Repeated rollback is unchanged;
a later manual confirmation conflicts even if its key is identical. Unknown
receipt formats are rejected and require a fresh reviewed dry-run; this branch's
new tables/receipt format have never been deployed, so no legacy receipt
compatibility or production backfill is provided.

Apply updates only derived projection/cache state and correction receipts.
Hub immutable observations/snapshots/Markdown and app raw URL/SHA/date/category/
Markdown/index and weekly membership remain untouched. No historical content
or synchronization signature is silently recomputed.

Dictionary changes use a new forward revision; article correction rollback does
not downgrade the dictionary and cannot replay an old replica over a new one.
Production application, three-end revision acknowledgement and live corrected
article evidence require a separately authorized rollout; test receipts are not
production receipts.
