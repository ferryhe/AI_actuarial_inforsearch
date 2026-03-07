# AI Actuarial Info Search

## Project Overview
AI-powered system for discovering, downloading, and cataloging AI-related documents from actuarial organizations worldwide. Features a Flask backend API, React frontend prototype, AI chatbot with RAG-powered Q&A, and multi-provider LLM support.

## Architecture
- **Backend**: Python 3.11 + Flask (port 8000, "Flask API" workflow)
- **Frontend**: React + Vite + Tailwind v4 (port 5000, "Start application" workflow)
- **Database**: SQLite (local at `data/index.db`)
- **AI/ML**: OpenAI, DeepSeek, Mistral providers; FAISS for vector search; sentence-transformers for embeddings
- **API Proxy**: Vite proxies `/api/*` requests to Flask on port 8000

## Key Directories
- `ai_actuarial/` - Core Python package (crawler, catalog, storage, web app)
- `ai_actuarial/web/` - Flask web application (templates, static assets, API routes)
- `client/` - React frontend source
  - `client/src/pages/` - Dashboard, Database, Chat, Tasks, Knowledge, Settings
  - `client/src/components/` - Layout (sidebar, header, i18n context, theme toggle), TagSelect (multi-select tag picker)
  - `client/src/hooks/` - useI18n (EN/ZH), useTheme (dark mode), useTaskOptions (dynamic backend data for task forms)
  - `client/src/lib/` - API helper (`api.ts`), class merging (`utils.ts`)
- `config/` - YAML configuration (sites, categories, AI providers)
- `config/backups/` - Auto-generated timestamped backups of sites.yaml (created before imports, restores, and periodically before site edits)
- `data/` - Downloads, database, logs, task outputs
- `doc_to_md/` - Document-to-Markdown conversion engines

## Running the App
- **Flask API**: `python3 -m ai_actuarial web --host 0.0.0.0 --port 8000` (console workflow)
- **React Frontend**: `npx vite --port 5000` (webview workflow)
- **Config**: `config/sites.yaml` (main config), `.env` (API keys/secrets)

## React Frontend Pages
- **Dashboard** (`/`) - Stats cards, quick actions, recent files
- **Database** (`/database`) - File browser with search, filters, pagination, download
- **Chat** (`/chat`) - AI chatbot with conversation management, mode/KB selection, citations
- **Tasks** (`/tasks`) - 9 task types in a grid: Site Configuration (YAML import/export, site CRUD, per-site crawl, backup management), Web Crawl, URL, File Import, Search, Catalog, Markdown, Chunk, RAG Index. Below the grid: standalone Scheduled Tasks section (CRUD for generic recurring tasks, scheduler status, reinit).
- **Knowledge** (`/knowledge`) - RAG knowledge base management, chunk profiles
- **Settings** (`/settings`) - Backend config, LLM providers, search engines, AI models, Task History (admin-only, collapsible with log viewer)

## YAML Config Backup System
- Backend auto-backs up `config/sites.yaml` to `config/backups/sites_YYYYMMDD_HHMMSS.yaml` before imports, restores, and site edits (throttled to max 1 backup per 5 min for edits)
- API endpoints: `POST /api/config/sites/import` (merge/overwrite + preview mode), `GET /api/config/sites/export`, `GET /api/config/sites/sample`, `GET /api/config/backups`, `POST /api/config/backups/restore`, `POST /api/config/backups/delete`
- Import supports both `{ sites: [...] }` JSON and `{ yaml_text: "..." }` raw YAML parsing
- Frontend uses fetch+blob download for export/sample (auth-compatible)

## Design System
- Fonts: Inter (body), Source Serif 4 (headings)
- Colors: Blue/indigo primary (HSL 221 83% 53%), CSS custom properties
- Dark mode: `.dark` class toggle, stored in localStorage
- i18n: English/Chinese via `useI18n()` hook with `t("key")` pattern
- Components: Card-based layout, framer-motion animations, lucide-react icons

## Key Features
- Web crawling across actuarial org sites
- PDF/Word/PPT download and deduplication
- AI-powered cataloging with keywords/summaries
- RAG chatbot with knowledge base management
- Markdown document conversion (marker, docling, mistral, deepseekocr engines)
- Multi-language support (EN, ZH)

## Configuration
- API keys go in `.env` file (see `.env.example`)
- Site/AI config in `config/sites.yaml`
- Auth mode: `REQUIRE_AUTH=false` (default, guest read-only)
