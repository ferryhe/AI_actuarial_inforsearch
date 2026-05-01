# AI Actuarial Info Search

[English](README.md) | [简体中文](README.zh-CN.md)

AI Actuarial Info Search helps actuarial and insurance teams discover, download, catalog, convert, and query AI-related documents from public organizations and local files.

The active product stack is **FastAPI + React**:

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
- Configure multiple AI providers, including OpenAI, DeepSeek, Mistral, and compatible providers.
- Operate through a React UI for dashboard, database, tasks, settings, knowledge, chat, logs, users, and file detail workflows.

## Quick Start

### Requirements

- Python 3.10+
- Node.js 18+
- Optional AI/search provider API keys in `.env` or `config/sites.yaml`
- Stable `TOKEN_ENCRYPTION_KEY` if provider credentials are stored in the database
- `FASTAPI_SESSION_SECRET` if email/session login is enabled

### Start The API

```bash
pip install -r requirements.txt
python -m ai_actuarial api --host 127.0.0.1 --port 8000
```

### Start The React UI

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api/*` to `http://127.0.0.1:8000`.

## Authentication

- `REQUIRE_AUTH=true`: users must log in with a session or token.
- `REQUIRE_AUTH=false`: guests get read-only access.
- `FASTAPI_SESSION_COOKIE_SECURE=true`: mark session cookies as HTTPS-only. If omitted, this defaults to enabled when `FASTAPI_ENV=production` and `REQUIRE_AUTH=true`.
- Task execution, schedule management, settings writes, downloads, and deletes require appropriate token permissions.
- Local admin bootstrap can be configured with `BOOTSTRAP_ADMIN_TOKEN`; do not commit real tokens.

## Scheduled Task Parameters

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

Import local files:

```json
{
  "directory_path": "C:/path/to/files",
  "recursive": true,
  "extensions": ["pdf", "docx"],
  "target_subdir": "scheduled-imports"
}
```

Collect explicit URLs:

```json
{
  "urls": [
    "https://example.org/report.pdf"
  ]
}
```

Supported intervals include `daily`, `weekly`, `daily at 02:00`, `every 6 hours`, and `every 30 minutes`.

## Project Layout

```text
AI_actuarial_inforsearch/
├─ ai_actuarial/           # Core Python package and FastAPI API
├─ client/                 # React + TypeScript frontend
├─ config/                 # YAML configuration
├─ data/                   # Local runtime data, downloads, logs, and SQLite DB
├─ doc_to_md/              # Document-to-Markdown engines
├─ docs/                   # Architecture, guides, plans, and reports
├─ scripts/                # Maintenance scripts
├─ tests/                  # Python and source-level tests
├─ vite.config.ts          # Vite dev server and build config
├─ package.json            # Node dependencies and scripts
└─ requirements.txt        # Python runtime dependencies
```

## Configuration

Main structured configuration lives in `config/sites.yaml`. Secrets should stay in `.env` or process environment.
Provider API keys used at runtime should be saved as encrypted database credentials; `sites.yaml` should bind AI functions to provider/model and an optional credential id such as `openai:llm:instance:default`.

Important variables:

- `TOKEN_ENCRYPTION_KEY`: required for database-stored provider credentials.
- `FASTAPI_SESSION_SECRET`: required for session login.
- `FASTAPI_SESSION_COOKIE_SECURE`: set to `true` for HTTPS deployments; defaults on when `FASTAPI_ENV=production` and auth is required.
- `BOOTSTRAP_ADMIN_TOKEN`: optional local/admin bootstrap token.
- `REQUIRE_AUTH`: enables full authentication when `true`.
- `BRAVE_API_KEY`, `SERPAPI_API_KEY`, `SERPER_API_KEY`, `TAVILY_API_KEY`: optional search keys.
- `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `SILICONFLOW_API_KEY`: optional AI/conversion keys.

Generate a Fernet key for `TOKEN_ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Diagnose the active embedding runtime without printing secrets:

```bash
python scripts/diagnose_embedding_runtime.py --config config/sites.yaml --json
```

More details:

- [AI Provider Credentials](docs/guides/AI_PROVIDER_CREDENTIALS.md)
- [RAG Embeddings Runtime](docs/guides/RAG_EMBEDDINGS_RUNTIME.md)

## Build And Test

```bash
npm run build
python -m pytest tests/test_fastapi_entrypoint.py tests/test_fastapi_no_flask_runtime.py tests/test_react_fastapi_authority.py tests/test_fastapi_react_cleanup.py -q
```

## Deployment

The Docker and Caddy configuration is aligned to the FastAPI + React stack:

- API container: FastAPI on port `5000`
- Frontend container: Vite dev/preview on port `5173`
- Caddy: `/api/*` to API, all other routes to React

For details, see:

- [Architecture](docs/ARCHITECTURE.md)
- [API Migration Status](docs/API_MIGRATION_STATUS.md)
- [Service Start Guide](docs/guides/SERVICE_START_GUIDE.md)

## Output Artifacts

- Downloaded files: `data/files/`
- SQLite database: `data/index.db`
- Catalog outputs: `data/catalog.jsonl`, `data/catalog.md`
- Update logs: `data/updates/`
- Application log: `data/app.log`
- Task logs: `data/task_logs/*.log`
