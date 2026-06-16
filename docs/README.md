# Documentation Index

This directory keeps maintained documentation first. Historical implementation reports, old phase plans, dated test notes, and legacy security summaries have been moved under [`archive/`](archive/README.md) so they do not read like current product status.

## Current References

- [Root README](../README.md): current product overview, final roadmap status, setup, feature set, and common commands.
- [Chinese README](../README.zh-CN.md): Chinese product overview and setup notes.
- [Security Policy](../SECURITY.md): maintained security posture and production checklist.
- [Architecture](ARCHITECTURE.md): current FastAPI + React architecture, standard/Agentic RAG modes, Markdown conversion, weekly updates, and web-listening rule surfaces.
- [API Migration Status](API_MIGRATION_STATUS.md): source of truth for the React/FastAPI boundary and maintained representative native API surfaces.
- [Deployment Runbook](deployment-runbook.md): deployment operations.
- [Rate Limiting](rate-limit-config.md): active rate-limit behavior for product endpoints and auth credential submissions.

## Operational Guides

- [Service Start Guide](guides/SERVICE_START_GUIDE.md): local and Docker startup commands.
- [Production Security Config](guides/PRODUCTION_SECURITY_CONFIG.md): server-local security environment values.
- [AI Provider Credentials](guides/AI_PROVIDER_CREDENTIALS.md): provider credential storage and binding contract.
- [AI Model Catalog](guides/AI_MODEL_CATALOG.md): model dropdown sources, cache refresh, and live discovery behavior.
- [Agentic RAG Guide](guides/AGENTIC_RAG.md): ready-data profiles, manifest build/status APIs, Agentic Chat behavior, and eval smoke commands.
- [RAG Embeddings Runtime](guides/RAG_EMBEDDINGS_RUNTIME.md): embeddings runtime resolution and diagnostics.
- [Troubleshooting Model Fetching](guides/TROUBLESHOOTING_MODEL_FETCHING.md): model registry troubleshooting.
- [Database Backend Guide](guides/DATABASE_BACKEND_GUIDE.md): database backend notes.
- [Gitee Mirror Sync](guides/GITEE_MIRROR_SYNC.md): optional mirror synchronization notes.

## Current Product Milestones

- FastAPI is the only product API authority for `/api/*`; React is the only maintained product UI.
- Security/RBAC hardening is merged, including upload-batch file import, SSRF checks, scoped permissions, auth rate limits, and bounded Chat document context.
- Agentic RAG is complete: KB ready-data manifests, `general` / `regulation` / `formula` profiles, deterministic read tools, Agentic Chat, structured citations, tool traces, and CI-backed eval smoke coverage.
- Final Feishu-plan roadmap items are complete on `main`:
  - Markdown conversion config split into `config/markdown_conversion.yaml` plus Settings/runtime integration.
  - Customer-facing Dashboard focused on document sources, categories, weekly additions, details, and Agent entry points.
  - `web-listening-agent-rule.v1` draft/validate/materialize workflow.
  - Weekly updates API/storage/task runtime using `files.first_seen`.
  - Knowledge-base-first Chat UI plus API/types/session extraction.
- Valid remote Copilot/review follow-up comments from the roadmap PR sequence were handled in dedicated follow-up PRs before the backlog was marked complete.

## Historical Archive

[`archive/`](archive/README.md) contains older dated plans, phase reports, code-review notes, manual test guides, older Chinese implementation docs, and prior security summaries. They are preserved for traceability but may reference obsolete Flask/Replit-era behavior, old phases, or work that has since been superseded.

When adding or updating docs, prefer current guides under `docs/guides/` for maintained behavior and add historical one-off reports under `docs/archive/`.
