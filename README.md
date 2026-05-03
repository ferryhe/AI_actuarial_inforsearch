# AI Actuarial Info Search

[English](README.md) | [Simplified Chinese](README.zh-CN.md)

AI Actuarial Info Search helps actuarial and insurance teams discover, download, catalog, convert, and query AI-related documents from public organizations and local files.

The active product stack is FastAPI + React:

| Surface | Stack | Local URL | Role |
| --- | --- | --- | --- |
| Product API | Python + FastAPI | `http://127.0.0.1:8000/api/*` | Single authority for product APIs |
| Product UI | React 19 + TypeScript + Vite | `http://127.0.0.1:5173` | Maintained web interface |

The old server-rendered HTML runtime and Replit workflow files have been retired. React routes should call native FastAPI endpoints only.

## Features

- Crawl actuarial and insurance organization sites.
- Expand discovery with optional search providers such as Brave and SerpAPI.
- Download PDF, Word, PowerPoint, Excel, and HTML sources.
- Deduplicate files with SHA256.
- Catalog files incrementally with summaries, keywords, and categories.
- Convert documents to Markdown with local or API-backed engines.
- Manage RAG knowledge bases, chunk profiles, and indexing jobs.
- Chat with documents through retrieval-augmented generation.
- Configure AI/search provider credentials from Settings.
- Operate through the React UI for dashboard, database, tasks, settings, knowledge, chat, logs, users, and file detail workflows.

## Quick Start

Requirements:

- Python 3.10+
- Node.js 18+
- `FASTAPI_SESSION_SECRET` in `.env`
- `TOKEN_ENCRYPTION_KEY` in `.env`
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
- `CONFIG_WRITE_AUTH_TOKEN`, `LOGS_READ_AUTH_TOKEN`, `FILE_DELETION_AUTH_TOKEN`: optional compatibility tokens. Leave unset unless you intentionally require matching `X-Auth-Token`.

Feature switches such as authentication, global logs, file deletion, rate limiting, CSRF protection, error-detail exposure, and security headers live in `config/sites.yaml -> features` and can be changed from Settings. If a matching environment variable is set, it is treated as a deployment override and the Settings page marks that value as locked.

The canonical SQLite path is `config/sites.yaml -> paths.db`. `DB_PATH` is only a fallback when that YAML path is absent.

## Authentication

- `features.require_auth=true`: users must log in with a session or token.
- `features.require_auth=false`: guests get read-only access.
- `FASTAPI_SESSION_COOKIE_SECURE=true`: marks session cookies as HTTPS-only. If omitted, this defaults to enabled when `FASTAPI_ENV=production` and auth is required.
- Task execution, schedule management, settings writes, downloads, and deletes require appropriate permissions.
- Local admin recovery can be configured with `BOOTSTRAP_ADMIN_TOKEN`; do not commit real tokens.

## Scheduled Tasks

In Tasks -> Configured Tasks, the `parameters` field must be valid JSON. These values are passed to the native background task when the schedule fires.

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

Import local files:

```json
{
  "directory_path": "C:/path/to/files",
  "recursive": true,
  "extensions": ["pdf", "docx"],
  "target_subdir": "scheduled-imports"
}
```

Supported intervals include `daily`, `weekly`, `daily at 02:00`, `every 6 hours`, and `every 30 minutes`.

## Project Layout

```text
AI_actuarial_inforsearch/
|-- ai_actuarial/           # Core Python package and FastAPI API
|-- client/                 # React + TypeScript frontend
|-- config/                 # YAML configuration
|-- data/                   # Local runtime data, downloads, logs, and SQLite DB
|-- doc_to_md/              # Document-to-Markdown engines
|-- docs/                   # Architecture, guides, plans, and reports
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
```

## More Details

- [Architecture](docs/ARCHITECTURE.md)
- [AI Provider Credentials](docs/guides/AI_PROVIDER_CREDENTIALS.md)
- [AI Model Catalog](docs/guides/AI_MODEL_CATALOG.md)
- [Rate Limiting](docs/rate-limit-config.md)
- [Service Start Guide](docs/guides/SERVICE_START_GUIDE.md)
