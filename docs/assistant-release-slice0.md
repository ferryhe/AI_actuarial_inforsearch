# Assistant skill release readiness (slice 0)

The runtime reads the `assistant/default` release slots from PostgreSQL. An empty slot set is valid storage state, but the user-facing Assistant reports `ASSISTANT_SKILLS_NOT_READY` without using quota or a model. Users can still open the existing **Read user guide (no AI)** entry.

## Inspect readiness

Use the same authoritative config, `DATABASE_URL` (or its configured environment name), and `DATA_DIR` used by the API:

```powershell
$env:AI_ACTUARIAL_IGNORE_DOTENV = "1"
python -m ai_actuarial --config $env:CONFIG_PATH assistant-release status --json
```

The JSON `ready` field is the readiness decision. A successful read command can return exit code 0 with `ready: false`; inspect `state` and each required skill's active release, revision, and public-visible tools. `state` distinguishes `not_ready`, `partial`, and `disabled`. A `ready` result also checks both actual bilingual Guide queries through the registered Guide executor. Invalid published artifacts report `INVALID_SKILL_RELEASE`.

## Publish the shipped release set

Run the actual UAT for each shipped skill package and save its matching receipt JSON. A receipt must contain `result: "PASS"`, real nonempty evidence, the exact skill/version/artifact digests, code SHA, data version, and model used. This command does not generate or infer receipts. The code SHA must match `BUILD_GIT_SHA` when the running build supplies a full SHA.

Read the current revisions first, then pass all three receipt files and revisions:

```powershell
python -m ai_actuarial --config $env:CONFIG_PATH assistant-release publish `
  --source-ref "git:$env:BUILD_GIT_SHA" --code-sha $env:BUILD_GIT_SHA `
  --data-version "<tested-data-version>" --model "<tested-model>" `
  --receipt "usage_navigation=$env:DATA_DIR\receipts\usage_navigation.json" `
  --receipt "resources_updates=$env:DATA_DIR\receipts\resources_updates.json" `
  --receipt "document_research=$env:DATA_DIR\receipts\document_research.json" `
  --expected-revision usage_navigation=0 `
  --expected-revision resources_updates=0 `
  --expected-revision document_research=0 --json
```

The command validates and stages all three shipped packages before one CAS activation of only changed required slots. Exact existing versions are reused when their supplied receipts match; a version with different immutable content is rejected. A CAS conflict leaves pointers unchanged; read `status` again and retry with current revisions. A repeated no-op does not bump revisions. Feedback and other optional slots are not part of this publication set.

## Roll back one skill

Rollback changes only the named required skill and requires its current revision from `status`:

```powershell
python -m ai_actuarial --config $env:CONFIG_PATH assistant-release rollback document_research --expected-revision 2 --json
```

`ArtifactStore` keeps the prior release for each changed slot. The CLI does not perform a bulk rollback or alter the Assistant feature switch. Check `status` after publication or rollback.

For a deployed Linux container, use its effective `CONFIG_PATH` and `DATA_DIR`; receipts must be mounted or copied into a path readable inside the container:

```sh
docker exec ai-api python -m ai_actuarial assistant-release status --json
```
