# Documentation Index

This directory keeps current operational documentation first, with dated plans and reports retained only as project history.

## Current References

- [Architecture](ARCHITECTURE.md): current FastAPI + React system posture.
- [API Migration Status](API_MIGRATION_STATUS.md): source of truth for the React/FastAPI boundary.
- [Deployment Runbook](deployment-runbook.md): deployment operations.
- [OpenAPI Overview](openapi.md) and [OpenAPI Schemas](openapi-schemas.md): API reference exports.

## Operational Guides

- [Service Start Guide](guides/SERVICE_START_GUIDE.md): local and Docker startup commands.
- [AI Provider Credentials](guides/AI_PROVIDER_CREDENTIALS.md): provider credential storage and binding contract.
- [RAG Embeddings Runtime](guides/RAG_EMBEDDINGS_RUNTIME.md): embeddings runtime resolution and diagnostics.
- [Troubleshooting Model Fetching](guides/TROUBLESHOOTING_MODEL_FETCHING.md): model registry troubleshooting.
- [Database Backend Guide](guides/DATABASE_BACKEND_GUIDE.md): database backend notes.

## Engineering Notes

- `architecture/`: subsystem design and interface notes that still help explain active code.
- `implementation/`: dated implementation reports and PR summaries.
- `testing/`: manual testing guides and checklists.
- `security/`: security summaries and hardening notes.
- `zh-cn/`: Chinese user and implementation docs.

## Historical Material

- `plans/`: dated plans. Keep only plans that still describe active or upcoming work.
- `archive/`: deprecated or historical documents kept for reference.
- `code_review/`: older review findings and progress notes.

When adding or updating docs, prefer current guides under `docs/guides/` for maintained behavior. Avoid adding new one-off plan documents after implementation unless they remain useful for future work.
