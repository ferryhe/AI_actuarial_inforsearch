# AI Actuarial Info Search

[English](README.md) | [Simplified Chinese](README.zh-CN.md)

AI Actuarial Info Search helps actuarial and insurance teams discover, download, catalog, convert, and query AI-related documents from public organizations and browser-selected local files.

The active product stack is **FastAPI + React**:

| Surface | Stack | Local URL | Role |
| --- | --- | --- | --- |
| Product API | Python + FastAPI | `http://127.0.0.1:8000/api/*` | Single authority for product APIs |
| Product UI | React 19 + TypeScript + Vite | `http://127.0.0.1:5173` | Maintained web interface |

The old server-rendered HTML runtime and Replit workflow files have been retired. React routes should call native FastAPI endpoints only.

## Current Status

The 2026 security/RBAC rollout is complete on `main`:

- Browser file import uses upload batches from the user's machine; active `type=file` collection runs require an upload batch, not an arbitrary server `directory_path`.
- Public URL fetching is protected by SSRF checks, redirect revalidation, and unsafe-address rejection.
- Permissions distinguish `sites.write`, `schedule.write`, `tasks.run`, and admin-only server filesystem helper authority.
- Chat/RAG document comparison accepts at most 3 selected document sources, bounds document context size, reports truncation notices, and labels retrieved/document context as untrusted in prompts.
- Login and registration submissions are IP-scoped rate limited before session mutation, with user-friendly 429 and 5xx error messages in the UI.
- There are no open security rollout PRs at the time this README was updated; PRs #118-#122 are merged.

## Features

- Crawl configured actuarial and insurance organization sites.
- Expand discovery with optional search providers such as Brave and SerpAPI.
- Download PDF, Word, PowerPoint, Excel, and HTML sources.
- Import browser-selected local files and folders through upload batches.
- Deduplicate files with SHA256.
- Catalog files incrementally with summaries, keywords, and categories.
- Convert documents to Markdown with local or API-backed engines.
- Manage RAG knowledge bases, chunk profiles, and indexing jobs.
- Chat with documents through retrieval-augmented generation and compare up to 3 selected document sources per request.
- Configure AI/search provider credentials from Settings.
- Operate through the React UI for dashboard, database, tasks, settings, knowledge, chat, logs, users, and file detail workflows.

## Quick Start

Requirements:

- Python 3.10+
- Node.js 18+
- `FASTAPI_SESSION_SECRET` in `.env` when session login is enabled
- `TOKEN_ENCRYPTION_KEY` in `.env` when provider credentials are stored in the database
- Provider credentials saved in Settings as encrypted DB credentials

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

## Configuration

There are three sources, each with a clear role:

- `config/sites.yaml`: non-secret runtime configuration, including AI routing, paths, RAG settings, search settings, scheduled tasks, and `features`.
- Encrypted DB credentials: provider API keys and base URLs, managed from Settings.
- `.env`: process secrets and explicit deployment overrides only.

Provider API keys should not be committed to YAML or kept long term in `.env`. Save them from Settings as encrypted DB credentials, then bind AI routes in `sites.yaml` to stable credential ids such as `openai:llm:instance:default`.

Important `.env` variables:

- `FASTAPI_SESSION_SECRET`: required for browser session login.
- `TOKEN_ENCRYPTION_KEY`: required to decrypt provider credentials stored in the database. Keep it stable.
- `BOOTSTRAP_ADMIN_TOKEN`: optional local/admin recovery token.
- `FASTAPI_CORS_ORIGINS`: allowed browser origins for deployed API access.
- `TRUST_PROXY`: set `true` only when direct API access is restricted to trusted reverse proxy traffic.
- `CONFIG_WRITE_AUTH_TOKEN`, `LOGS_READ_AUTH_TOKEN`, `FILE_DELETION_AUTH_TOKEN`: optional compatibility tokens. Leave unset unless you intentionally require matching `X-Auth-Token`.

Feature switches such as authentication, global logs, file deletion, rate limiting, CSRF protection, error-detail exposure, and security headers live in `config/sites.yaml -> features` and can be changed from Settings. If a matching environment variable is set, it is treated as a deployment override and the Settings page marks that value as locked.

The canonical SQLite path is `config/sites.yaml -> paths.db`. `DB_PATH` is only a fallback when that YAML path is absent.

## Authentication And Permissions

- `features.require_auth=true`: users must log in with a session or token.
- `features.require_auth=false`: guests get read-only access.
- `FASTAPI_SESSION_COOKIE_SECURE=true`: marks session cookies as HTTPS-only. If omitted, this defaults to enabled when the effective FastAPI environment is production and auth is required. `FASTAPI_ENV` overrides `config/sites.yaml -> server.fastapi_env`.
- Task execution, schedule management, settings writes, downloads, deletes, and site config writes require appropriate permissions.
- `operator` users can manage sites. `files.import.server` is reserved for admin-only server filesystem helper surfaces and is not part of the normal browser upload flow.
- Local admin recovery can be configured with `BOOTSTRAP_ADMIN_TOKEN`; do not commit real tokens.

## File Import And Tasks

For normal users, file import means selecting files or folders in the browser. The UI stages upload batches from the user's local machine and does not ask the server to read arbitrary client paths.

`type=file` collection runs require an `upload_batch_id`. A request that supplies only `directory_path` is rejected; do not document or expose arbitrary server-path import as a normal operator workflow.

In **Tasks -> Configured Tasks**, the `parameters` field must be valid JSON. These values are passed to the native background task when the schedule fires.

Common examples:

```json
{}
```

Catalog only files from one configured site:

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

Supported intervals include `daily`, `weekly`, `daily at 02:00`, `every 6 hours`, and `every 30 minutes`.

## Security Posture

- Configure production security values through server-local environment variables; see [Production Security Config](docs/guides/PRODUCTION_SECURITY_CONFIG.md).
- Rate limiting is implemented by FastAPI middleware; see [Rate Limiting](docs/rate-limit-config.md).
- Chat/RAG selected-document context is bounded and marked untrusted before it reaches the LLM.
- Public URL fetching is checked for unsafe schemes, private/reserved IPs, redirect target changes, and DNS/IP drift.
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
|-- docs/                   # Architecture, guides, historical plans, and reports
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

## Build And Test

```bash
npm run build
python -m pytest tests/test_fastapi_entrypoint.py tests/test_fastapi_no_flask_runtime.py tests/test_react_fastapi_authority.py tests/test_fastapi_react_cleanup.py -q
python -m pytest tests/test_fastapi_auth_endpoints.py tests/test_auth_react_source.py tests/test_fastapi_chat_endpoints.py tests/test_tasks_react_source.py -q
```

## More Details

- [Documentation Index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API Migration Status](docs/API_MIGRATION_STATUS.md)
- [AI Provider Credentials](docs/guides/AI_PROVIDER_CREDENTIALS.md)
- [AI Model Catalog](docs/guides/AI_MODEL_CATALOG.md)
- [Rate Limiting](docs/rate-limit-config.md)
- [Production Security Config](docs/guides/PRODUCTION_SECURITY_CONFIG.md)
- [Service Start Guide](docs/guides/SERVICE_START_GUIDE.md)
