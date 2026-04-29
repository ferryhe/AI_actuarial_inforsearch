# Architecture

## Current Product Posture

`AI_actuarial_inforsearch` is a document-intelligence platform for actuarial and insurance research workflows.

The active product stack is:

```text
React SPA -> FastAPI /api -> native FastAPI routers
```

The legacy server-rendered web assets have been removed from the runtime tree. New product behavior should be implemented in `client/` and `ai_actuarial/api/`.

## Core System Chain

```text
site config
-> crawling / web collection
-> file download + SHA256 dedupe
-> cataloging + markdown conversion
-> semantic chunking + embeddings
-> knowledge base indexing
-> RAG retrieval + chat
-> React operations UI
```

## Frontend / Backend Split

### Frontend Surface

- **React SPA** (`client/`) is the only maintained product UI.
- Vite proxies `/api/*` to FastAPI during local development.

### Backend Surface

- **FastAPI** (`ai_actuarial/api/`) is the only product API authority for `/api/*`.
- Unmatched `/api/*` requests return `410` until a native FastAPI route is added.

## Architectural Rule

1. New product APIs go under `ai_actuarial/api/routers/`.
2. Routed React product paths must depend only on native FastAPI routes.
3. Do not add product UI code under `ai_actuarial/web`; that tree has been retired.
4. Do not add direct non-API route proxies for auth pages; `/login` and `/register` are React routes using `/api/auth/*`.
5. Keep deployment config aligned with FastAPI + React only.

## Key Subsystems

### Collection and Cataloging

- `ai_actuarial/cli.py`
- `ai_actuarial/crawler.py`
- `ai_actuarial/collectors/*`
- `ai_actuarial/catalog.py`
- `ai_actuarial/catalog_incremental.py`

### Storage and Database

- `ai_actuarial/storage.py`
- `ai_actuarial/storage_v2.py`
- `ai_actuarial/storage_v2_full.py`
- `ai_actuarial/storage_factory.py`
- `ai_actuarial/db_models.py`

### Web and API

- `client/`
- `ai_actuarial/api/app.py`
- `ai_actuarial/api/routers/*`
- `ai_actuarial/api/services/*`

### RAG and Chat

- `ai_actuarial/rag/knowledge_base.py`
- `ai_actuarial/rag/semantic_chunking.py`
- `ai_actuarial/rag/indexing.py`
- `ai_actuarial/rag/vector_store.py`
- `ai_actuarial/chatbot/router.py`
- `ai_actuarial/chatbot/retrieval.py`
- `ai_actuarial/chatbot/conversation.py`

### Document Conversion

- `doc_to_md/registry.py`
- `doc_to_md/engines/*`
- `doc_to_md/pipeline/text_extraction.py`

## Runtime Verification

- `GET /api/health`
- `GET /api/migration/status`
- `GET /api/migration/inventory` when `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`

Expected local development:

```bash
python -m ai_actuarial api --host 127.0.0.1 --port 8000
npm run dev
```
