# AI Actuarial Info Search

[English](README.md) | [Simplified Chinese](README.zh-CN.md)

AI Actuarial Info Search is a FastAPI + React document-intelligence platform for actuarial and insurance research. It discovers, downloads, catalogs, converts, searches, and chats with public web documents and browser-uploaded local files.

## Current Status

`main` now reflects the completed 2026 product consolidation and Feishu-plan roadmap:

- **Runtime:** FastAPI is the only `/api/*` authority; React/Vite is the only maintained product UI. The legacy server-rendered/Replit-era workflow is retired.
- **Security/RBAC:** session/token auth, scoped permissions, upload-batch file import, SSRF-safe public URL fetch, auth/rate-limit hardening, and bounded untrusted Chat document context are active.
- **Customer product surface:** the Dashboard is customer-facing first: sources, categories, weekly additions, document detail, and Agent entry points. Backend processing metrics live in admin/ops pages instead of the homepage.
- **Document conversion:** Markdown conversion is driven by `config/markdown_conversion.yaml` and Settings. Tool ordering, format routing, paid/API-tool enablement, and tuning are configurable; paid/API tools are not auto-selected by default.
- **Collection automation:** configured crawls, search-provider fallback, browser-upload file imports, scheduled tasks, and web-listening rule draft/validate/materialize workflows are supported.
- **Weekly updates:** `/api/weekly-updates` and `/api/weekly-updates/latest` summarize newly discovered files using `files.first_seen`.
- **RAG and Chat:** standard vector RAG and Agentic RAG coexist. Chat is knowledge-base first, keeps conversation/session history, and supports standard multi-KB chat plus single-ready-KB Agentic mode.
- **Roadmap completion:** Agentic RAG PRs #133-#145 plus roadmap PRs #147-#154 are merged; the managed backlog in `.hermes/project-status.md` is complete.

## Feature Set

### Discovery, ingestion, and catalog

- Crawl configured actuarial and insurance organization sites.
- Expand discovery with optional Brave/SerpAPI-style search providers.
- Download PDF, Word, PowerPoint, Excel, and HTML sources.
- Import browser-selected local files/folders through upload batches.
- Deduplicate files with SHA-256 and incrementally catalog summaries, keywords, and categories.
- Generate weekly-update summaries from newly discovered files.

### Markdown conversion

- Convert documents to Markdown with local or API-backed engines.
- Configure conversion behavior in `config/markdown_conversion.yaml` or Settings.
- Route tools by format, tune scan/page limits, and keep paid/API tools opt-in.

### Web-listening rules

- Draft `web-listening-agent-rule.v1` YAML rules from a source URL and acquisition goal.
- Validate rule YAML before applying it.
- Materialize validated rules into acquisition profile, monitor task, section selection, and monitor scope configuration.

### RAG, Agentic RAG, and Chat

- Manage RAG knowledge bases, files, categories, chunk profiles, and indexing jobs.
- Chat with knowledge bases through standard vector RAG.
- Compare up to 3 selected document sources per request.
- Build Agentic RAG `ready_data` manifests for `general`, `regulation`, or `formula` profiles.
- Use Agentic RAG Chat for one ready knowledge base with deterministic evidence, structured citations, and an inspectable tool trace.
- Search ready data directly through summary, title, section, relation, formula, table, and calculation-term tools.

### Admin and operations

- Configure AI/search provider credentials from Settings as encrypted database credentials.
- Manage sites, schedules, tasks, logs, users, security settings, model catalogs, and knowledge bases through React UI.
- Keep production secrets in `.env`/environment and encrypted DB credential storage, not committed YAML.

## Quick Start

Requirements:

- Python 3.10+
- Node.js `^20.19.0` or `>=22.12.0` for the Vite 7 frontend toolchain
- Java 11+ on `PATH` only when using OpenDataLoader PDF conversion
- `FASTAPI_SESSION_SECRET` when session login is enabled
- stable `TOKEN_ENCRYPTION_KEY` when provider credentials are stored in the database

Start the API:

```bash
pip install -r requirements.txt
python -m ai_actuarial api --host 127.0.0.1 --port 8000
```

Start the React UI:

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api/*` to `http://127.0.0.1:8000`.

If `http://127.0.0.1:5173/` returns `404`, another Node/Vite process may be listening on that port. Start the project UI with `npm run dev` from this repository and use the URL printed by Vite.

## Core Configuration

There are four active configuration sources:

- `config/sites.yaml`: non-secret runtime configuration, including sites, paths, AI routing, RAG, search, schedules, features, and web-listening materialized config.
- `config/markdown_conversion.yaml`: Markdown conversion tool order, format routing, paid-tool enablement, and tuning.
- Encrypted database credentials: provider API keys and base URLs, managed from Settings.
- `.env` / process environment: deployment secrets and explicit production overrides only.

Provider API keys should not be committed to YAML or kept long term in `.env`. Save them from Settings as encrypted DB credentials, then bind AI routes in `sites.yaml` to stable credential IDs such as `openai:llm:instance:default`.

Important variables:

- `FASTAPI_SESSION_SECRET`: required for browser session login.
- `TOKEN_ENCRYPTION_KEY`: required to decrypt provider credentials stored in the database. Keep it stable.
- `BOOTSTRAP_ADMIN_TOKEN`: optional local/admin recovery token.
- `FASTAPI_CORS_ORIGINS`: allowed browser origins for deployed API access.
- `TRUST_PROXY`: set `true` only when direct API access is restricted to trusted reverse proxy traffic.
- `CONFIG_WRITE_AUTH_TOKEN`, `LOGS_READ_AUTH_TOKEN`, `FILE_DELETION_AUTH_TOKEN`: optional compatibility tokens. Leave unset unless intentionally requiring matching `X-Auth-Token`.

Feature switches such as authentication, global logs, file deletion, rate limiting, CSRF protection, error-detail exposure, and security headers live in `config/sites.yaml -> features` and can be changed from Settings. Matching environment variables are deployment overrides and are shown as locked in Settings.

The canonical SQLite path is `config/sites.yaml -> paths.db`. `DB_PATH` is only a fallback when that YAML path is absent.

## Authentication and Permissions

- `features.require_auth=true`: users must log in with a session or token.
- `features.require_auth=false`: guests get read-only access.
- Task execution, schedule management, settings writes, downloads, deletes, and site config writes require scoped permissions.
- `operator` users can manage sites. `files.import.server` is reserved for admin-only server filesystem helper surfaces and is not part of normal browser upload flow.
- Local admin recovery can be configured with `BOOTSTRAP_ADMIN_TOKEN`; do not commit real tokens.

## File Import and Tasks

Normal file import means selecting files or folders in the browser. The UI stages upload batches from the user's local machine and does not ask the server to read arbitrary client paths.

`type=file` collection runs require an `upload_batch_id`. A request that supplies only `directory_path` is rejected; do not expose arbitrary server-path import as a normal operator workflow.

In **Tasks -> Configured Tasks**, the `parameters` field must be valid JSON. Supported intervals include `daily`, `weekly`, `daily at 02:00`, `every 6 hours`, and `every 30 minutes`.

Common task parameter examples:

```json
{}
```

Catalog one configured site:

```json
{
  "site": "Society of Actuaries (SOA)",
  "batch": 50,
  "max_chars": 12000,
  "retry_errors": false
}
```

Run a configured site crawl:

```json
{
  "site": "Casualty Actuarial Society (CAS)"
}
```

Run a weekly summary task:

```json
{
  "period_start": "2026-06-01T00:00:00+00:00",
  "period_end": "2026-06-08T00:00:00+00:00",
  "max_files": 500
}
```

## Agentic RAG

Agentic RAG is a structured evidence layer on top of the existing catalog, chunks, knowledge-base registry, and chat product. It does not replace standard vector RAG; the two modes coexist:

| Mode | Entry point | Data dependency | Main constraints |
| --- | --- | --- | --- |
| Standard RAG | `/api/chat/query` with default `rag_mode` | Vector indexes and retrieved chunks | Multi-KB and direct selected-document context are allowed |
| Agentic RAG Chat | `/api/chat/query` with `rag_mode="agentic"` | One ready KB manifest | Exactly one ready KB; no direct document context |
| Agentic read APIs | `/api/agentic-rag/*` | KB manifest or explicit allowed `output_dir` | Deterministic tool results / answer |

Knowledge bases carry a `manifest_profile`:

| Profile | Main artifacts | Use case |
| --- | --- | --- |
| `general` | `doc_catalog.jsonl`, `sections.jsonl`, `ready_data_manifest.json` | General research/internal documents |
| `regulation` | General artifacts plus aliases, summaries, structured sections, and relations | Regulations, standards, compliance documents |
| `formula` | Regulation artifacts plus formula cards, structured tables, and calculation terms | Actuarial formula and calculation-heavy documents |

Build a ready-data manifest from the CLI:

```bash
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile formula --validate
```

Run deterministic eval smoke:

```bash
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```

See [Agentic RAG Guide](docs/guides/AGENTIC_RAG.md) for profiles, APIs, UI behavior, storage paths, and eval commands.

## Security Posture

- Configure production security values through server-local environment variables; see [Production Security Config](docs/guides/PRODUCTION_SECURITY_CONFIG.md).
- Rate limiting is implemented by FastAPI middleware; see [Rate Limiting](docs/rate-limit-config.md).
- Chat/RAG selected-document context is bounded and marked untrusted before it reaches the LLM.
- Public URL fetching checks unsafe schemes, private/reserved IPs, redirect target changes, and DNS/IP drift.
- Browser auth pages show friendly rate-limit and system-error messages without exposing internals.

See [Security Policy](SECURITY.md) for the maintained security checklist.

## Project Layout

```text
AI_actuarial_inforsearch/
|-- ai_actuarial/           # Core Python package and FastAPI API
|-- client/                 # React + TypeScript frontend
|-- config/                 # YAML configuration
|-- data/                   # Local runtime data, downloads, logs, and SQLite DB
|-- doc_to_md/              # Document-to-Markdown engines
|-- docs/                   # Current docs plus archived historical notes
|-- scripts/                # Maintenance scripts
|-- tests/                  # Python and source-level tests
|-- vite.config.ts          # Vite dev server and build config
|-- package.json            # Node dependencies and scripts
`-- requirements.txt        # Python runtime dependencies
```

## Diagnostics

Diagnose secret and credential state without printing secret values:

```bash
python scripts/diagnose_secrets_runtime.py --json
```

Generate a Fernet key for `TOKEN_ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Build and Test

```bash
npm run build
python -m pytest tests/test_fastapi_entrypoint.py tests/test_fastapi_no_flask_runtime.py tests/test_react_fastapi_authority.py tests/test_fastapi_react_cleanup.py -q
python -m pytest tests/test_fastapi_auth_endpoints.py tests/test_auth_react_source.py tests/test_fastapi_chat_endpoints.py tests/test_tasks_react_source.py -q
python -m pytest tests/test_markdown_conversion_config.py tests/test_web_listening_rule.py tests/test_weekly_updates.py -q
python -m pytest tests/agentic_rag/test_eval.py tests/agentic_rag/test_planner_agentic_loop.py -q
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```

## More Details

- [Documentation Index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API Migration Status](docs/API_MIGRATION_STATUS.md)
- [AI Provider Credentials](docs/guides/AI_PROVIDER_CREDENTIALS.md)
- [AI Model Catalog](docs/guides/AI_MODEL_CATALOG.md)
- [Agentic RAG Guide](docs/guides/AGENTIC_RAG.md)
- [Rate Limiting](docs/rate-limit-config.md)
- [Production Security Config](docs/guides/PRODUCTION_SECURITY_CONFIG.md)
- [Service Start Guide](docs/guides/SERVICE_START_GUIDE.md)
- [Archived historical docs](docs/archive/README.md)
