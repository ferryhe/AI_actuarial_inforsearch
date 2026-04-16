# AI Actuarial Info Search

## Project Overview
AI-powered system for discovering, downloading, and cataloging AI-related documents from actuarial organizations worldwide. The current product contract is a FastAPI backend + React frontend, with Flask retained only for legacy HTML pages and a shrinking set of historical handlers.

## Architecture
- **Backend**: Python 3.11 + FastAPI gateway (port 8000, primary product API workflow)
- **Legacy backend surface**: Flask app mounted behind FastAPI only for legacy HTML pages and limited historical debugging
- **Frontend**: React + Vite + Tailwind v4 (port 5000, webview workflow)
- **Database**: SQLite (local at `data/index.db`)
- **AI/ML**: OpenAI, DeepSeek, Mistral providers; FAISS for vector search; sentence-transformers for embeddings
- **API Proxy**: Vite proxies `/api/*` requests to FastAPI on port 8000

## Key Directories
- `ai_actuarial/` - Core Python package (crawler, catalog, storage, FastAPI gateway, legacy web app)
- `ai_actuarial/api/` - FastAPI routers, services, migration inventory, authority guard
- `ai_actuarial/web/` - Legacy Flask application (HTML pages + historical compatibility code)
- `client/` - React frontend source
  - `client/src/pages/` - Dashboard, Database, Chat, Tasks, Knowledge, Settings, Login/Register/Profile/Users
  - `client/src/components/` - Layout, TagSelect, ConfirmDeleteModal
  - `client/src/hooks/` - useI18n, useTheme, useTaskOptions
  - `client/src/lib/` - API helper (`api.ts`), class merging (`utils.ts`)
- `config/` - YAML configuration (sites, categories, AI providers)
- `config/backups/` - Timestamped `sites.yaml` backups
- `data/` - Downloads, database, logs, task outputs
- `doc_to_md/` - Document-to-Markdown conversion engines

## Running the App
- **FastAPI product API**: `python3 -m ai_actuarial api --host 0.0.0.0 --port 8000`
- **Legacy Flask-only server (historical/debug only)**: `python3 -m ai_actuarial web --host 0.0.0.0 --port 8000`
- **React Frontend**: `npx vite --port 5000`
- **Config**: `config/sites.yaml` (main config), `.env` (API keys/secrets)

## API authority notes
- Routed React product pages must call **native FastAPI** endpoints only.
- Unmatched `/api/*` requests are blocked by default in FastAPI-authority mode.
- To temporarily debug an unported historical Flask endpoint through the gateway, set `FASTAPI_ALLOW_LEGACY_API_FALLBACK=1`.
- Detailed migration inventory is available only when `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`.

## Product surfaces
- **Dashboard** (`/`) - Stats cards, quick actions, recent files
- **Database** (`/database`) - File browser with search, filters, pagination, export/download/delete flows
- **File Detail** (`/file-detail`) - Metadata edit, markdown edit, chunk generation, preview/download/delete
- **File Preview** (`/file-preview`) - Side-by-side source preview + chunk view
- **Chat** (`/chat`) - AI chatbot with conversation management, citations, retrieved blocks
- **Tasks** (`/tasks`) - Site/task operations, scheduler controls, task history
- **Knowledge** (`/knowledge`) - Knowledge-base and chunk-profile management
- **KB Detail** (`/knowledge/:kbId`) - File/category bindings, indexing, stats
- **Settings** (`/settings`) - Native settings shell (read-focused in current product path)
- **Logs** (`/logs`) - Native log/task-history shell
- **Users** (`/users`) - Admin user management
- **Login/Register/Profile** - FastAPI-native auth/user flows

## Key features
- Web crawling across actuarial org sites
- PDF/Word/PPT download and deduplication
- AI-powered cataloging with keywords/summaries
- RAG chatbot with knowledge base management
- Markdown document conversion (marker, docling, mistral, deepseekocr engines)
- Multi-language support (EN, ZH)
