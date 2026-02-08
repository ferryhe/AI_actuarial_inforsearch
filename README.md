# AI Actuarial Info Search

AI Actuarial Info Search is a system for discovering, downloading, and cataloging AI-related documents from actuarial organizations worldwide, with a modern web interface for managing collections and data.

## Purpose

Help actuarial teams stay current on AI/ML developments through reliable discovery, structured cataloging, and a production-ready management UI.

## Key Features

- Web crawling and discovery across actuarial organization sites
- Optional web search expansion via Brave and SerpAPI
- Keyword-based filtering with multi-language support
- Downloads for PDF, Word, PowerPoint, Excel, and HTML sources
- SHA256-based deduplication to prevent duplicates
- Incremental cataloging with summaries, keywords, and categories
- SQLite for local use and PostgreSQL for production
- Web interface for search, export, and operational management

## Web Interface Capabilities

- Database browser with sorting, selection, and CSV export
- Site management with keyword and prefix exclusions
- Task center for running and monitoring collections
- Global logs for operational visibility
- Local file import with directory browsing

## Project Structure (High-Level)

- `ai_actuarial/` core package (crawler, catalog, storage, collectors, processors)
- `ai_actuarial/web/` web application (Flask app, templates, assets)
- `config/` site and category configuration
- `data/` downloaded files, catalogs, and database
- `docs/` implementation notes and operational guidance

## Operations Manual

- Service start guide (Linux + Windows): `20260208_SERVICE_START_GUIDE.md`

## Configuration Notes

- Web search keys: `BRAVE_API_KEY`, `SERPAPI_API_KEY`
- File deletion: set `ENABLE_FILE_DELETION=true` before starting the web service

## Documentation Index

- Quick start: `QUICK_START_NEW_FEATURES.md`
- Reference: `QUICK_REFERENCE.md`
- Database backend guide: `DATABASE_BACKEND_GUIDE.md`
- Modular system guide: `MODULAR_SYSTEM_GUIDE.md`
- Implementation and summaries: `docs/`

## Output Artifacts

- Downloaded files under `data/files/`
- Index database at `data/index.db` (SQLite) or PostgreSQL backend
- Incremental catalog outputs: `data/catalog.jsonl` and `data/catalog.md`
- Update logs under `data/updates/`

---

AI Actuarial Info Search is built to keep actuarial teams current on AI/ML developments with reliable discovery, structured cataloging, and a production-ready management UI.
