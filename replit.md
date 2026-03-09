# AI Actuarial Info Search

## Project Overview
This branch is the Flask-only archive baseline for AI Actuarial Info Search. It preserves the server-rendered Flask UI, REST API, AI chatbot with RAG-powered Q&A, and the existing Python business logic without the React/Vite frontend.

## Architecture
- **Backend**: Python 3.11 + Flask (port 8000)
- **Frontend**: Flask templates rendered by the backend
- **Database**: SQLite (local at `data/index.db`)
- **AI/ML**: OpenAI, DeepSeek, Mistral providers; FAISS for vector search; sentence-transformers for embeddings

## Key Directories
- `ai_actuarial/` - Core Python package (crawler, catalog, storage, web app)
- `ai_actuarial/web/` - Flask web application (templates, static assets, API routes)
- `config/` - YAML configuration (sites, categories, AI providers)
- `data/` - Downloads, database, logs, task outputs
- `doc_to_md/` - Document-to-Markdown conversion engines

## Running the App
- `python3 -m ai_actuarial web --host 0.0.0.0 --port 8000`
- Main config: `config/sites.yaml`
- Secrets/config overrides: `.env`

## Notes
- This branch intentionally removes the React/Vite application.
- Use this branch as the rollback/archive baseline before the FastAPI migration branch diverges.
