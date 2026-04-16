# Architecture

## Current product posture

`AI_actuarial_inforsearch` is a document-intelligence platform for actuarial/insurance research workflows.

Core system chain:

```text
site config
-> crawling / web collection
-> file download + SHA256 dedupe
-> cataloging + markdown conversion
-> semantic chunking + embeddings
-> knowledge base indexing
-> RAG retrieval + chat
-> web operations UI
```

## Frontend / backend split

### Frontend surfaces
- **React SPA** (`client/`) — long-term primary product UI
- **Flask template UI** (`ai_actuarial/web/app.py`) — legacy server-rendered UI retained for compatibility

### Backend surfaces
- **FastAPI gateway** (`ai_actuarial/api/`) — the **only long-term and current product API authority** for `/api/*`
- **Flask web app** (`ai_actuarial/web/`) — mounted only for legacy HTML pages and a shrinking set of historical API handlers kept for temporary debugging/reference

## Architectural rule

### API authority rule

**FastAPI is the only long-term authority for `/api/*` routes.**

That means:
1. New product APIs must be added under `ai_actuarial/api/routers/`
2. Flask `/api/*` routes are temporary historical surfaces only
3. Routed React product paths must depend only on native FastAPI routes
4. Unmatched `/api/*` requests should be blocked by the FastAPI authority guard unless debugging explicitly enables fallback
5. Flask should continue to serve legacy HTML pages until they are retired

## Runtime composition today

```text
React SPA -> FastAPI /api -> native FastAPI routers
                         -> authority guard blocks unported /api fallback by default

Legacy HTML UI -> Flask directly
```

## Migration target

Target steady state:

```text
React SPA -> FastAPI only
Legacy HTML UI -> Flask pages only (or later retired)
Flask /api remains only as non-product historical code until fully removed
```

## Key subsystems

### 1. Collection and cataloging
- `ai_actuarial/cli.py`
- `ai_actuarial/crawler.py`
- `ai_actuarial/collectors/*`
- `ai_actuarial/catalog.py`
- `ai_actuarial/catalog_incremental.py`

### 2. Storage and database
- `ai_actuarial/storage.py`
- `ai_actuarial/storage_v2.py`
- `ai_actuarial/storage_v2_full.py`
- `ai_actuarial/storage_factory.py`
- `ai_actuarial/db_models.py`

### 3. Web and API
- `ai_actuarial/web/app.py`
- `ai_actuarial/web/chat_routes.py`
- `ai_actuarial/web/rag_routes.py`
- `ai_actuarial/api/app.py`
- `ai_actuarial/api/routers/*`

### 4. RAG and chat
- `ai_actuarial/rag/knowledge_base.py`
- `ai_actuarial/rag/semantic_chunking.py`
- `ai_actuarial/rag/indexing.py`
- `ai_actuarial/rag/vector_store.py`
- `ai_actuarial/chatbot/router.py`
- `ai_actuarial/chatbot/retrieval.py`
- `ai_actuarial/chatbot/conversation.py`

### 5. Document conversion
- `doc_to_md/registry.py`
- `doc_to_md/engines/*`
- `doc_to_md/pipeline/text_extraction.py`

## Current migration guidance

For route-level status, see:
- `docs/API_MIGRATION_STATUS.md`
- runtime endpoint: `GET /api/migration/status`
- runtime inventory endpoint: `GET /api/migration/inventory` (ops/debug only, enable with `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`)

Operational note:
- unmatched `/api/*` requests are blocked by default in FastAPI-authority mode
- set `FASTAPI_ALLOW_LEGACY_API_FALLBACK=1` only when you intentionally need to debug an unported historical Flask endpoint
