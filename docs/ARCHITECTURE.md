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

The Feishu-plan roadmap PR-A through PR-I (#156-#164) is complete on `main`: Markdown conversion config, customer Dashboard, typed scheduled tasks, weekly summaries, `full_pipeline` chaining, web-listening rules, and KB-first Chat are active product surfaces rather than future phases.

## Core System Chain

```text
site config + markdown conversion config
-> crawling / web collection / web-listening rule materialization
-> file download + SHA256 dedupe
-> cataloging + Markdown conversion
-> weekly-update summaries from first_seen files
-> optional full_pipeline chaining across collection, Markdown, catalog, chunking, and RAG indexing
-> semantic chunking + embeddings
-> knowledge base indexing
-> standard RAG retrieval + KB-first chat
-> optional Agentic RAG ready_data build + deterministic evidence loop
-> React customer/admin operations UI
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
7. Dashboard should stay customer-facing by default; operational processing metrics belong in admin/ops routes.
8. Markdown conversion behavior belongs in `config/markdown_conversion.yaml` plus Settings, not hard-coded tool order lists.
9. Web-listening rule materialization must preserve the typed `web-listening-agent-rule.v1` contract and create scheduled `full_pipeline` monitors, not collection-only tasks.

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
- `client/src/pages/Dashboard.tsx`: customer-facing sources/categories/weekly updates/Agent entry point.
- `client/src/pages/Chat.tsx`: KB-first Chat surface for standard and Agentic RAG modes.
- `ai_actuarial/api/app.py`
- `ai_actuarial/api/routers/*`
- `ai_actuarial/api/services/*`

### Web-listening Rules

- `ai_actuarial/web_listening_rule.py`: `web-listening-agent-rule.v1` schema and validation.
- `ai_actuarial/api/services/ops_write.py`: draft/validate/materialize operations.
- Materialized config lives in the standard site/schedule config surfaces and uses scheduled `full_pipeline` tasks with `source_collection_type: scheduled`, `check_database: true`, and RAG indexing disabled unless explicitly requested.

### Weekly Updates

- `ai_actuarial/api/services/weekly_updates.py`: summary generation from `files.first_seen`.
- `weekly_update_summaries` storage table and `weekly_summary` collection task; default scheduling uses `relative_period: previous_week` for the completed UTC ISO week.
- `/api/weekly-updates` and `/api/weekly-updates/latest` expose summaries to Dashboard/product UI.

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

- `config/markdown_conversion.yaml`: active non-secret conversion policy.
- `ai_actuarial/markdown_conversion_config.py`: normalization, defaults, and persisted config handling.
- `doc_to_md/registry.py`
- `doc_to_md/engines/*`
- `doc_to_md/pipeline/text_extraction.py`

## Runtime Verification

- `GET /api/health`
- `GET /api/migration/status`
- `GET /api/migration/inventory` when `FASTAPI_ENABLE_MIGRATION_INVENTORY=1`
- `GET /api/config/markdown-conversion`
- `GET /api/weekly-updates/latest`
- `POST /api/web-listening/rules/validate`
- `POST /api/collections/run` with `type: full_pipeline`
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
