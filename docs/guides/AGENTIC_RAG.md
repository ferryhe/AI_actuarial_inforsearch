# Agentic RAG Guide

Agentic RAG is the structured evidence layer added on top of the existing catalog, chunks, knowledge-base registry, and chat product.

It does not replace standard vector RAG. The product now supports two RAG paths:

- **Standard RAG**: vector-index retrieval plus LLM answer generation. It supports multi-KB chat and direct selected-document context.
- **Agentic RAG**: deterministic local tools over ready_data artifacts. It requires one Agentic-ready knowledge base, returns structured evidence/citations, and records the tool trace used to produce the answer.

## Current Status

The planned Agentic RAG implementation sequence is merged on `main`:

- PR0: retrieval eval baseline and `eval/cases.jsonl`.
- PR1: L0 ready_data builder MVP.
- PR2: `agentic_ready_manifests` registry, KB `manifest_profile`, and Knowledge UI build/status actions.
- PR3: L0 summary/title read tools and `/api/agentic-rag/search/*` endpoints.
- PR4: L1 regulation profile, aliases, structured sections, relations, and relation tracing.
- PR5a: backend deterministic agentic loop and `/api/agentic-rag/chat`.
- PR5b: Chat UI integration through `rag_mode="agentic"`, evidence rendering, and tool trace display.
- PR6: L2 formula profile with formula cards, structured tables, calculation terms, and formula tools.
- PR7: Agentic answer/evidence eval, structured citation coverage, no-evidence refusal checks, and CI smoke coverage.

## Profiles And Artifacts

Ready data is written as JSON/JSONL artifacts. The supported profiles are defined in `ai_actuarial/agentic_rag/manifest_profiles.py`.

| Profile | Main artifacts | Purpose |
| --- | --- | --- |
| `general` | `doc_catalog.jsonl`, `sections.jsonl`, `ready_data_manifest.json` | Basic document catalog and section evidence |
| `regulation` | General profile plus `title_aliases.jsonl`, `doc_summaries.jsonl`, `sections_structured.jsonl`, `relations_graph.json` | Regulation, standard, and compliance documents |
| `formula` | Regulation profile plus `formula_cards.jsonl`, `tables_structured.jsonl`, `calculation_terms.jsonl` | Formula-heavy actuarial documents, tables, and calculation terms |

Knowledge-base-scoped builds are stored under the database-adjacent ready-data directory:

```text
<db-parent>/agentic_ready_data/kbs/<kb_id>/<profile>/1/
```

When using the default local SQLite path, this is normally:

```text
data/agentic_ready_data/kbs/<kb_id>/<profile>/1/
```

## Build Ready Data

Build from the CLI:

```bash
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile general --validate
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile regulation --validate
python -m ai_actuarial.agentic_rag.ready_data_builder --db data/index.db --kb-id <kb-id> --profile formula --validate
```

Build from the product API:

```http
POST /api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest/build
```

Read manifest status:

```http
GET /api/rag/knowledge-bases/{kb_id}/agentic-ready-manifest
```

The Knowledge UI exposes the same profile and build/status controls. KB list/detail payloads include:

- `manifest_profile`
- `agentic_ready_manifest`
- `agentic_ready_available`
- `agentic_fallback_mode`

## Read Tools And APIs

Direct ready_data read APIs require `catalog.read` permission:

```http
POST /api/agentic-rag/search/summaries
POST /api/agentic-rag/search/titles
POST /api/agentic-rag/search/sections
POST /api/agentic-rag/search/formula-cards
POST /api/agentic-rag/search/tables
POST /api/agentic-rag/search/calculation-terms
POST /api/agentic-rag/trace/relations
POST /api/agentic-rag/chat
```

Requests can resolve ready data either from a KB registry entry:

```json
{
  "query": "How is net premium calculated?",
  "kb_id": "my-kb",
  "profile": "formula",
  "limit": 5
}
```

or, in tests and local diagnostics, from an explicit `output_dir`:

```json
{
  "query": "How is net premium calculated?",
  "output_dir": "eval/fixtures/agentic_ready_data",
  "profile": "formula",
  "limit": 5
}
```

The service rejects path escapes and does not allow explicit `output_dir` to be mixed with KB registry lookup.

## Chat Behavior

The Chat UI has a Standard / Agentic RAG selector.

Agentic mode is intentionally narrower than standard RAG:

- exactly one knowledge base must be selected;
- the selected KB must have a ready Agentic manifest;
- direct selected-document context and `document_sources` are rejected;
- the backend stores the conversation and quota usage through `/api/chat/query`, just like standard chat;
- assistant metadata includes `rag_mode="agentic"`, `model="agentic-ready-data"`, `tool_trace`, `kb_id`, `profile`, `output_dir`, and evidence counts.

Agentic answers are deterministic summaries from ready_data evidence. They do not call an external LLM in the current implementation.

## Evaluation

Retrieval baseline:

```bash
python -m ai_actuarial.agentic_rag.eval --mode retrieval --cases eval/cases.jsonl --json
```

Agentic answer/evidence smoke:

```bash
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```

The Agentic evaluator checks:

- expected evidence document hits;
- expected evidence source hits;
- structured citation coverage using real citation records;
- no-evidence refusal behavior;
- forbidden unsupported answer terms;
- strict JSONL case schema.

GitHub CI runs:

```bash
python -m pytest tests/agentic_rag/test_eval.py -q
python -m ai_actuarial.agentic_rag.eval --mode agentic --cases eval/agentic_cases.jsonl --output-dir eval/fixtures/agentic_ready_data --profile formula --json
```

## Operational Notes

- Agentic ready_data artifacts are derived from existing catalog/chunk data and are not secrets, but they may contain document text. Treat the ready_data directory with the same access controls as the source database and converted documents.
- Provider credentials are still needed for standard chat, embeddings, cataloging, and OCR. Current Agentic read tools and eval smoke do not require external provider credentials.
- Standard RAG remains the right mode for open-ended multi-KB chat and direct selected-document comparison. Agentic RAG is the right mode when a KB has been prepared into structured ready_data and the user needs traceable evidence.
