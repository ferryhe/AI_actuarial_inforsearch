# AI Actuarial Info Search

## Project Overview
AI-powered system for discovering, downloading, and cataloging AI-related documents from actuarial organizations worldwide. Features a Flask web interface, AI chatbot with RAG-powered Q&A, and multi-provider LLM support.

## Architecture
- **Backend**: Python 3.11 + Flask
- **Database**: SQLite (local at `data/index.db`)
- **Frontend**: Flask templates + vanilla JS (server-rendered)
- **AI/ML**: OpenAI, DeepSeek, Mistral providers; FAISS for vector search; sentence-transformers for embeddings

## Key Directories
- `ai_actuarial/` - Core Python package (crawler, catalog, storage, web app)
- `ai_actuarial/web/` - Flask web application (templates, static assets, routes)
- `config/` - YAML configuration (sites, categories, AI providers)
- `data/` - Downloads, database, logs, task outputs
- `doc_to_md/` - Document-to-Markdown conversion engines
- `docs/` - Project documentation

## Running the App
- **Workflow**: `python3 -m ai_actuarial web --host 0.0.0.0 --port 5000`
- **Config**: `config/sites.yaml` (main config), `.env` (API keys/secrets)

## Key Features
- Web crawling across actuarial org sites
- PDF/Word/PPT download and deduplication
- AI-powered cataloging with keywords/summaries
- RAG chatbot with knowledge base management
- Markdown document conversion (marker, docling, mistral, deepseekocr engines)
- Multi-language support (EN, ZH, FR, DE, etc.)

## Configuration
- API keys go in `.env` file (see `.env.example`)
- Site/AI config in `config/sites.yaml`
- Auth mode: `REQUIRE_AUTH=false` (default, guest read-only)
