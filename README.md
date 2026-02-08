# AI Actuarial Info Search

A system for discovering, downloading, and cataloging AI-related documents from actuarial organizations worldwide, with a modern web interface for managing collections and data.

## Core Capabilities

- **Web Crawling & Discovery**: Crawl actuarial organization sites and discover AI/ML-related documents.
- **Web Search Integration**: Optional Brave and SerpAPI search to expand discovery beyond configured sites.
- **Smart Filtering**: Keyword-based inclusion/exclusion with multi-language support.
- **File Acquisition**: Download PDFs, Word, PowerPoint, Excel, and HTML sources.
- **Strict Deduplication**: SHA256-based content matching to prevent duplicates.
- **Catalog Generation**: Summaries, keywords, and categories extracted from downloaded files.
- **Database Flexibility**: SQLite for local use and PostgreSQL for production.

## Web Interface Features

- **Database Browser**: Advanced searchable tables with sorting, selection, CSV export, and bulk actions.
- **Site Management**: Add/edit sources with keyword and prefix exclusions.
- **Task Center**: Run collections, view execution history, and monitor active tasks.
- **Global Logs**: Centralized operational logs for monitoring and debugging.
- **Smart Import**: Local file ingestion with directory browsing.

## Data & Workflow Features

- **Modular Collection Workflows**: URL collection, file import, scheduled, and ad-hoc runs.
- **Incremental Cataloging**: Track processed files and update only changes.
- **Category System**: Centralized category definitions for consistent classification.
- **Exports**: CSV, JSON, and Markdown exports of indexed files and catalog data.

## Security & Quality

- **Safe Data Handling**: HTML escaping and CSV injection prevention in exports.
- **Configurable Deletion**: File deletion gated by feature flag for safety.
- **Operational Transparency**: Audit-friendly logs and task history.

## Project Structure (High-Level)

- `ai_actuarial/` core package (crawler, catalog, storage, collectors, processors)
- `ai_actuarial/web/` web application (Flask app, templates, assets)
- `config/` site and category configuration
- `data/` downloaded files, catalogs, and database
- `docs/` implementation notes and operational guidance

## Output Artifacts

- Downloaded files stored by domain under `data/files/`
- Index database at `data/index.db` (SQLite) or PostgreSQL backend
- Incremental catalog outputs: `data/catalog.jsonl` and `data/catalog.md`
- Update logs under `data/updates/`

---

AI Actuarial Info Search is built to keep actuarial teams current on AI/ML developments with reliable discovery, structured cataloging, and a production-ready management UI.
