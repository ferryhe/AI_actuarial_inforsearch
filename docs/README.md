# Documentation Index

This directory keeps current operational documentation first.

## Current References

- [Root README](../README.md): current product overview, setup, security/Agentic RAG status, and common commands.
- [Chinese README](../README.zh-CN.md): Chinese product overview and setup notes.
- [Security Policy](../SECURITY.md): maintained security posture and production checklist.
- [Architecture](ARCHITECTURE.md): current FastAPI + React + standard/Agentic RAG system posture.
- [API Migration Status](API_MIGRATION_STATUS.md): source of truth for the React/FastAPI boundary, including Agentic RAG API surfaces.
- [Deployment Runbook](deployment-runbook.md): deployment operations.
- [OpenAPI Overview](openapi.md) and [OpenAPI Schemas](openapi-schemas.md): API reference exports.
- [Rate Limiting](rate-limit-config.md): active rate-limit behavior for product endpoints and auth credential submissions.

## Operational Guides

- [Service Start Guide](guides/SERVICE_START_GUIDE.md): local and Docker startup commands.
- [Production Security Config](guides/PRODUCTION_SECURITY_CONFIG.md): server-local security environment values.
- [AI Provider Credentials](guides/AI_PROVIDER_CREDENTIALS.md): provider credential storage and binding contract.
- [AI Model Catalog](guides/AI_MODEL_CATALOG.md): model dropdown sources, cache refresh, and live discovery behavior.
- [Agentic RAG Guide](guides/AGENTIC_RAG.md): ready_data profiles, manifest build/status APIs, Agentic Chat behavior, and eval smoke commands.
- [RAG Embeddings Runtime](guides/RAG_EMBEDDINGS_RUNTIME.md): embeddings runtime resolution and diagnostics.
- [Troubleshooting Model Fetching](guides/TROUBLESHOOTING_MODEL_FETCHING.md): model registry troubleshooting.
- [Database Backend Guide](guides/DATABASE_BACKEND_GUIDE.md): database backend notes.

## Current Product Milestones

- FastAPI is the only product API authority for `/api/*`; React is the only maintained product UI.
- Security/RBAC hardening is merged, including upload-batch file import, SSRF checks, scoped permissions, auth rate limits, and bounded Chat document context.
- Agentic RAG is merged through PR #142 and documented in [Agentic RAG Guide](guides/AGENTIC_RAG.md). It adds KB ready_data manifests, `general` / `regulation` / `formula` profiles, deterministic read tools, Agentic Chat, structured citations, tool traces, and CI-backed eval smoke coverage.
- PR #145 added the post-plan QA fixes for CJK ready_data query matching, Agentic Chat KB section-count labels, and raw Agentic score display.

## Engineering Notes

- `architecture/`: subsystem design and interface notes that still help explain active code.
- `implementation/`: dated implementation reports and PR summaries.
- `testing/`: manual testing guides and checklists.
- `security/`: older security summaries and hardening notes. Treat them as dated engineering notes, not as the active checklist.
- `zh-cn/`: Chinese user and implementation docs.

When adding or updating docs, prefer current guides under `docs/guides/` for maintained behavior.
