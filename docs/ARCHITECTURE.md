# Architecture

## Current Product Posture

`AI_actuarial_inforsearch` is a document-intelligence platform for actuarial and insurance research workflows.

The active product stack is:

```text
React SPA -> FastAPI /api -> native FastAPI routers
```

The legacy server-rendered web assets have been removed from the runtime tree. New product behavior should be implemented in `client/` and `ai_actuarial/api/`.

The active RAG posture has two paths:

- **Standard RAG**: vector indexes, embeddings, LLM-backed answer generation, multi-KB chat, and direct selected-document comparison.
- **Agentic RAG**: KB-scoped ready_data manifests, deterministic local read tools, structured evidence/citations, and tool traces for a single Agentic-ready KB.

## Core System Chain

```text
site config
-> crawling / web collection
-> file download + SHA256 dedupe
-> cataloging + markdown conversion
-> semantic chunking + embeddings
-> knowledge base indexing
-> standard RAG retrieval + chat
-> optional Agentic RAG ready_data build + deterministic evidence loop
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
6. Standard RAG and Agentic RAG must remain explicit modes; Agentic Chat currently requires exactly one ready KB and cannot be combined with direct document context.

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

### Agentic RAG

- `ai_actuarial/agentic_rag/manifest_profiles.py`: `general`, `regulation`, and `formula` ready_data profiles.
- `ai_actuarial/agentic_rag/ready_data_builder.py`: KB-scoped ready_data artifact builder and validator.
- `ai_actuarial/agentic_rag/ready_data_tools.py`: deterministic summary, title, section, relation, formula, table, and calculation-term tools.
- `ai_actuarial/agentic_rag/planner.py`: category/profile-aware tool plan selection.
- `ai_actuarial/agentic_rag/agentic_loop.py`: deterministic evidence loop and structured citations.
- `ai_actuarial/agentic_rag/eval.py`: retrieval baseline plus Agentic answer/evidence eval.
- `ai_actuarial/api/routers/agentic_rag.py`: direct ready_data search/chat APIs.
- `ai_actuarial/api/services/rag_admin.py`: manifest registry/status/build integration for KBs.

Product API/UI ready_data builds are constrained to the configured SQLite database-adjacent `agentic_ready_data/` directory, for example `data/agentic_ready_data/kbs/<kb_id>/<profile>/1/` when using the default local DB path. CLI runs default to `data/agentic_ready_data/...` unless `--output-dir` is provided.

## RAG Runtime Modes

| Mode | Entry point | Data dependency | Generation | Main constraints |
| --- | --- | --- | --- | --- |
| Standard RAG | `/api/chat/query` with default `rag_mode` | Vector indexes and retrieved chunks | LLM-backed | Multi-KB and direct selected-document context are allowed |
| Agentic RAG Chat | `/api/chat/query` with `rag_mode="agentic"` | One ready KB manifest | Deterministic ready_data answer | Exactly one ready KB; no direct document context |
| Agentic read APIs | `/api/agentic-rag/*` | KB manifest or explicit `output_dir` | Tool results / deterministic answer | `catalog.read`; output paths must stay under allowed ready_data roots |

### Document Conversion

- `doc_to_md/registry.py`
- `doc_to_md/engines/*`
- `doc_to_md/pipeline/text_extraction.py`

## Runtime Verification

- `GET /api/health`
- `GET /api/migration/status`
- `GET /api/migration/inventory` when `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`
- `GET /api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest`
- `POST /api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build`

Expected local development:

```bash
python -m ai_actuarial api --host 127.0.0.1 --port 8000
npm run dev
```

Agentic ready_data CLI smoke:

```bash
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile formula --validate
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```
