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
- **Markdown content management** - view, edit, and convert documents to markdown
- SQLite for local use and PostgreSQL for production
- Web interface for search, export, and operational management

## Web Interface Capabilities

- Database browser with sorting, selection, and CSV export
- Site management with keyword and prefix exclusions
- Task center for running and monitoring collections
- **Markdown conversion** - convert PDFs and documents to markdown format
- **File detail pages** - view and edit markdown content with live preview
- Global logs for operational visibility
- Local file import with directory browsing

## Markdown Feature

The system supports viewing, editing, and converting documents to markdown format:

### File Detail Page
- **View Mode**: Renders markdown content with proper formatting (headings, lists, code blocks, tables)
- **Edit Mode**: Edit markdown directly in a textarea with monospace font
- **Auto-save**: Markdown edits are saved with timestamp tracking
- **Source Tracking**: Tracks whether content is manual, converted, or original

### Markdown Conversion Task
- Select multiple files from the database for batch conversion
- Choose conversion tool: Marker (PDF-optimized), Docling (multi-format), or Auto-detect
- Option to overwrite existing markdown content
- Progress tracking and error reporting
- Currently uses a placeholder implementation - integrate with [doc_to_md](https://github.com/ferryhe/doc_to_md) tools for production use

### Database Storage
- Markdown content stored in `catalog_items` table
- Fields: `markdown_content` (TEXT), `markdown_updated_at` (TIMESTAMP), `markdown_source` (TEXT)
- Accessible via Storage API: `get_file_markdown()`, `update_file_markdown()`

## Project Structure (High-Level)

- `ai_actuarial/` core package (crawler, catalog, storage, collectors, processors)
- `ai_actuarial/web/` web application (Flask app, templates, assets)
- `config/` site and category configuration
- `data/` downloaded files, catalogs, and database
- `docs/` implementation notes and operational guidance

## Project Directory Overview

```
AI_actuarial_inforsearch/
├─ ai_actuarial/           # Core package (crawler, catalog, storage, web app)
├─ config/                 # Site and category configuration
├─ data/                   # Downloads, catalog outputs, and database
├─ docs/                   # Implementation notes and summaries
├─ scripts/                # Maintenance and helper scripts
├─ SERVICE_START_GUIDE.md  # Service start guide (Linux + Windows)
├─ QUICK_START_NEW_FEATURES.md
├─ QUICK_REFERENCE.md
├─ DATABASE_BACKEND_GUIDE.md
├─ MODULAR_SYSTEM_GUIDE.md
├─ README.md
└─ requirements.txt
```

## Operations Manual

- Service start guide (Linux + Windows): `SERVICE_START_GUIDE.md`

## System Architecture

```mermaid
flowchart LR
    subgraph Sources
        A[Actuarial Sites]
        B[Web Search APIs]
    end
    subgraph Core
        C[Crawler & Collectors]
        D[Storage Layer]
        E[Catalog Processor]
    end
    subgraph Data
        F[(SQLite/PostgreSQL)]
        G[data/files]
        H[data/catalog.*]
    end
    subgraph UI
        I[Flask Web App]
        J[Database Browser & Task Center]
    end

    A --> C
    B --> C
    C --> D
    C --> G
    D --> F
    E --> H
    D --> E
    D --> I
    I --> J
```

## Runtime Environment

| Component | Supported / Notes |
| --- | --- |
| Python | 3.10+ |
| Web Server | Flask (built-in dev server for local) |
| Database | SQLite (local), PostgreSQL (production) |
| Deployment | Docker + Docker Compose |
| Reverse Proxy | Caddy |
| OS | Windows (local), Linux (server) |

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
