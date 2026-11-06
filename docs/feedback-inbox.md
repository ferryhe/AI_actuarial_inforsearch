# Local feedback inbox

The existing [feedback API](feedback-api.md) remains the source of truth. These
commands use its authenticated management HTTP endpoints, never PostgreSQL,
Chat, a model, email, messaging or GitHub. Public intake may be disabled while
history is pulled, read and managed. No task is installed or enabled by default.

Copy `config/feedback-inbox.example.yaml` to an external runtime config. It may
also be a `feedback_inbox` section in the existing authoritative sites config.
Each entry requires a unique, stable `site_key`, an HTTP(S) base `url`, and a
`token_env` environment-variable name. The key must equal the deployment's
server identity. Keep the same key when its URL changes; do not reuse a key for
a different deployment. Duplicate/missing keys and embedded URL credentials are
rejected. Do not put tokens in YAML, command arguments or reports. Use HTTPS for
remote endpoints. The existing admin API token needs `feedback.read` for pull
and `feedback.manage` for mark. A missing/expired token returns an explicit
authentication failure; a credential lacking permission returns permission.

Use the same Windows account and `DATA_DIR`/`CONFIG_PATH` environment for manual
and scheduled runs. Renew the named token through the existing account/token
workflow when it expires. Do not modify production configuration to try this
example. `--config` goes before `feedback`, consistently with other CLI commands:

```powershell
python -m ai_actuarial --config C:\Runtime\feedback-inbox.yaml feedback pull --json
python -m ai_actuarial --config C:\Runtime\feedback-inbox.yaml feedback list
python -m ai_actuarial --config C:\Runtime\feedback-inbox.yaml feedback list --status new --site-key china --json
python -m ai_actuarial --config C:\Runtime\feedback-inbox.yaml feedback mark FEEDBACK-UUID --site-key china --status reviewed --json
python -m ai_actuarial --config C:\Runtime\feedback-inbox.yaml feedback mark FEEDBACK-UUID --site-key china --status closed --json
python -m ai_actuarial feedback --help
python -m ai_actuarial feedback pull --help
python -m ai_actuarial feedback list --help
python -m ai_actuarial feedback mark --help
```

`list` reads the **local cached state**, including complete submitted content,
anonymous/null or account user ID, original kind/source/page/locale and server
timestamps/status. It needs no remote credential and does not contact a server.
An ID shared by multiple sites requires `mark --site-key`. Mark requires a local
record, sends only `{"status":"reviewed"}` or `{"status":"closed"}`, and stores
the server response, including its authoritative status and update timestamp.
A failed HTTP request leaves the prior local record intact. An uncertain network
failure can still mean the server committed: repeat the same mark to read back
its authoritative response. A successful HTTP mark followed by a local write
failure is also reported as failure and retains the prior canonical local status.
Mark writes the readable report before committing canonical JSON; if canonical
replacement fails it restores the exact prior report (or its prior absence).
Repeat the same mark after fixing storage to recover the server's authoritative
status. Local failure does not roll back a server commit.

Files are confined to `<resolved data root>/feedback/`; `DATA_DIR` overrides
`paths.data` using the existing resolver:

| File | Purpose |
| --- | --- |
| `inbox.json` | Canonical complete business records, keyed by `(site_key, feedback_id)` |
| `inbox.md` | Original text/business metadata plus cached-state and per-site sync facts, refreshed after each site attempt |
| `sync.json` | Per-site last attempt, last full successful scan, counts and safe error category |
| `.lock` | OS-managed writer lock; released on process exit, including crashes |

Every pull scans `status=new` from cursor **0**; it does not use a durable
max-ID/timestamp watermark. It follows server page continuations, validates a
whole page and atomically replaces the complete JSON before advancing. Repeated
pulls deduplicate feedback by the composite key; equal timestamps, live new
writes and late commits with a lower ID are recovered by subsequent fresh
scans. Pull is GET-only and never changes server status. Existing local history
is retained even if a server returns no new records, another site fails or
public collection is disabled. Already reviewed/closed records are not removed.
Pull refreshes records still returned by the `new` scan; changes made by another
manager after a record leaves `new` are not a full remote-history reconciliation.

Each file replacement is atomic and flushed; the two report files are not one
filesystem transaction. Pull persists each complete JSON page before continuing;
after each site's sync evidence changes, it refreshes Markdown with the site
outcome, safe error category/message and last-success/attempt times. Default text
`list` shows the same facts and explicitly labels its records as local cached
state, not a live view. If pull's Markdown write fails after JSON succeeds, the
canonical record remains readable and the command fails; the next full scan
repairs the report. A failed JSON page is never continued. A site failure does not erase a prior
successful site's records or its last-success timestamp. Do not erase malformed
local files to hide an error: preserve them and repair before retrying. A shared
OS writer lock prevents overlapping manual/scheduled pulls or marks from losing
each other's updates; readers need no lock. There is no unattended retry loop:
the next run starts fresh. A busy writer returns failure; rerun later.

## JSON and exit contract v1

`--json` produces one ASCII-safe JSON object on stdout, including usage and
runtime failures (original Unicode is JSON-escaped, not altered). No credential, endpoint/configuration dump or traceback is
included. The fixed envelope is `schema_version`, `command`, `success`,
`outcome`, `items`, `sites`, `error`. `list` returns cached business items and
sync evidence; `mark` returns its one authoritative server item; `pull` returns
per-site outcomes and counts. `error` is null or `{code,message}`; site errors
have the same shape. Fixtures are `tests/fixtures/feedback_cli_contract.json`
and `tests/fixtures/feedback_cli.schema.json`. Usage errors are exit 2; with
`--json` they use the same envelope, otherwise standard argparse help goes to
stderr. `command=feedback` identifies usage without a recognized subcommand.
Use each command's `--help` for arguments.

| Exit | Meaning |
| --- | --- |
| 0 | Success, including `no_new_data` (distinct from failure) |
| 2 | Configuration/usage error, including ambiguous site identity |
| 3 | Missing, invalid or expired management credential |
| 4 | Permission denied |
| 5 | Connection/timeout failure |
| 6 | Other server HTTP failure |
| 7 | Local write failure |
| 8 | Invalid/unreadable local data |
| 9 | Invalid server page/record/JSON |
| 10 | Feedback/management endpoint not found |
| 11 | Another writer holds the inbox lock |

A partial pull returns the first failing site's nonzero category in configured
site order and `outcome=partial_failure`; inspect all `sites` entries. Full-site
success updates that site's `last_success_at` only after its final page; partial
pages remain safely cached. `new_count`/`updated_count` count applied pages.

## Independent Windows Task Scheduler setup (disabled)

These are manual setup instructions, not an installer run by the CLI. First run
the exact manual command and inspect `inbox.json`, `inbox.md` and `sync.json`.
Use an external config and a Python environment with this project's dependencies.
Ensure named credentials are available to the selected Windows user at task run
time; avoid storing tokens in task actions or logs. A user environment change
may require a fresh sign-in before Task Scheduler inherits it.

The following creates a **disabled**, separate task every 15 minutes while the
current user is signed in. Choose a unique name; `Register-ScheduledTask` is
intentionally used without `-Force` so an existing task is not overwritten.
The task working directory is the checkout, not Task Scheduler's default folder.
No existing collection, weekly or explanation task is touched.

```powershell
$repo = 'C:\Project\AI_actuarial_inforsearch'
$configPath = 'C:\Runtime\feedback-inbox.yaml'
$pythonPath = (Get-Command python).Source
$taskName = 'AIActuarial-FeedbackInbox-461'
$action = New-ScheduledTaskAction -Execute $pythonPath `
  -Argument ('-m ai_actuarial --config "{0}" feedback pull --json' -f $configPath) `
  -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(5)) `
  -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
  -LogonType Interactive -RunLevel Limited
$task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal
$task.Settings.Enabled = $false
Register-ScheduledTask -TaskName $taskName -InputObject $task
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
```

Keep the formal task disabled until independently accepted and explicitly
enabled for operations. These commands inspect or disable that exact task:

```powershell
Get-ScheduledTaskInfo -TaskName 'AIActuarial-FeedbackInbox-461'
Disable-ScheduledTask -TaskName 'AIActuarial-FeedbackInbox-461'
```

`LastTaskResult` is the CLI exit code above. `sync.json` supplies per-site failure
and last-success evidence; it never stores tokens. Compare its timestamp after
a run. A logged-out, sleeping or powered-off PC cannot poll; there is no uptime
guarantee or external notification. `IgnoreNew` prevents scheduled overlap and
the CLI lock also handles manual overlap. No automatic installation, activation,
email, message, GitHub Issue or model call occurs.
