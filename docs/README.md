# Documentation Index

This directory keeps current operational documentation first, with dated plans and reports retained only as project history.

## Current References

- [Root README](../README.md): current product overview, setup, security rollout status, and common commands.
- [Chinese README](../README.zh-CN.md): Chinese product overview and setup notes.
- [Security Policy](../SECURITY.md): maintained security posture and production checklist.
- [Architecture](ARCHITECTURE.md): current FastAPI + React system posture.
- [API Migration Status](API_MIGRATION_STATUS.md): source of truth for the React/FastAPI boundary.
- [Deployment Runbook](deployment-runbook.md): deployment operations.
- [OpenAPI Overview](openapi.md) and [OpenAPI Schemas](openapi-schemas.md): API reference exports.
- [Rate Limiting](rate-limit-config.md): active rate-limit behavior for product endpoints and auth credential submissions.

## Operational Guides

- [Service Start Guide](guides/SERVICE_START_GUIDE.md): local and Docker startup commands.
- [Production Security Config](guides/PRODUCTION_SECURITY_CONFIG.md): server-local security environment values.
- [AI Provider Credentials](guides/AI_PROVIDER_CREDENTIALS.md): provider credential storage and binding contract.
- [AI Model Catalog](guides/AI_MODEL_CATALOG.md): model dropdown sources, cache refresh, and live discovery behavior.
- [RAG Embeddings Runtime](guides/RAG_EMBEDDINGS_RUNTIME.md): embeddings runtime resolution and diagnostics.
- [Troubleshooting Model Fetching](guides/TROUBLESHOOTING_MODEL_FETCHING.md): model registry troubleshooting.
- [Database Backend Guide](guides/DATABASE_BACKEND_GUIDE.md): database backend notes.

## Engineering Notes

- `architecture/`: subsystem design and interface notes that still help explain active code.
- `implementation/`: dated implementation reports and PR summaries.
- `testing/`: manual testing guides and checklists.
- `security/`: older security summaries and hardening notes. Treat them as dated engineering notes, not as the active checklist.
- `zh-cn/`: Chinese user and implementation docs.

## Historical Material

- `archive/`: deprecated or historical documents kept for reference.
- `archive/plans/`: completed/superseded planning documents moved out of the active plan area.
- `archive/security/`: legacy Flask-era security review material and quick-fix guides that no longer match the FastAPI + React authority.
- `archive/guides/`: legacy quick-start, modular-system, and chatbot roadmap guides that predate the current FastAPI + React product contract.
- `plans/`: dated plans that may still describe active or future work. Completed rollout plans should be moved to `archive/plans/`.
- `code_review/`: older review findings and progress notes.

## Recent Archive Actions

After the 2026 security/RBAC rollout finished, these stale active docs were archived:

- `docs/guides/SECURITY_IMPROVEMENTS_GUIDE.md` -> `docs/archive/security/20260208_legacy_flask_security_improvements_guide.md`
- `docs/guides/REVIEW_SUMMARY.md` -> `docs/archive/security/20260208_legacy_security_review_summary.md`
- `docs/guides/CODE_REVIEW_REPORT.md` -> `docs/archive/security/20260208_legacy_code_review_report.md`
- legacy quick-start/modular/chatbot roadmap guides -> `docs/archive/guides/`
- completed FastAPI migration plans from April 2026 -> `docs/archive/plans/`
- completed February security hardening plan -> `docs/archive/plans/`

When adding or updating docs, prefer current guides under `docs/guides/` for maintained behavior. Avoid adding new one-off plan documents after implementation unless they remain useful for future work.
