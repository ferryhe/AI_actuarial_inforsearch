# OpenAPI / Swagger Documentation

## Overview

The AI Actuarial Info Search API is documented using OpenAPI 3.0 specifications. Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the server is running.

## API Base Information

- **Base URL**: `http://{host}:{port}/api`
- **Current Version**: `v1` (implicit in URL prefix `/api`)
- **Content-Type**: `application/json`

## Swagger UI Configuration

The FastAPI application is pre-configured with Swagger UI. Access it at:

```
/docs          → Swagger UI (interactive)
/redoc         → ReDoc (read-only documentation)
/openapi.json  → Raw OpenAPI 3.0 JSON schema
```

## API Versioning Strategy

### Current Approach
Currently the API uses path-based versioning: `/api/{resource}` with no explicit version prefix. All endpoints are considered `v1` implicitly.

### URL Path Versioning (Planned)
The planned path for explicit versioning when needed:

```
GET /api/v1/endpoint   → Current stable version
GET /api/v2/endpoint   → Next version (when available)
```

**Note**: Migrating from the current implicit `/api/` prefix to `/api/v1/` requires a coordinated front-end update. Until that migration is complete, the current `/api/` URLs are considered the stable v1 surface.

### Header-Based Versioning (Future)
When the API surface changes significantly, header-based versioning will be layered on top:

```
API-Version: 2024-01-01  (date-based version label)
```

This allows the same URL to serve different response shapes based on the requested version.

### Endpoints That Need Versioning Consideration
The following endpoints have complex response shapes or are likely to evolve and should be explicitly versioned when a v2 is introduced:

| Endpoint | Reason |
|----------|--------|
| `POST /api/chat/query` | LLM response format may change with model upgrades |
| `POST /api/rag/knowledge-bases/{kb_id}/index` | Indexing strategy evolves with RAG improvements |
| `GET /api/read/files` | Pagination and filter schema may expand |
| `POST /api/files-write/files/update` | File processing pipeline changes |

### Deprecation Policy

1. **Old versions are supported for at least 6 months** after a new version is released.
2. **Deprecation notice**: Endpoints planned for removal will return `Warning` headers:
   ```
   Warning: 299 - "Deprecated: /api/v1/endpoint will be removed in 2025-07-01. Use /api/v2/endpoint."
   ```
3. **Removal**: After the sunset date, the endpoint returns `410 Gone`.
4. **Communication**: Deprecations are announced in:
   - API response headers (Warning header)
   - Swagger UI (`/docs`) deprecation notices
   - Release notes

### Version Lifecycle

| Stage | Description |
|-------|-------------|
| **Current** | `/api/` implicit v1 — stable, supported |
| **Planned** | `/api/v1/` explicit — same surface as `/api/`, just explicit |
| **Future** | `/api/v2/` — new features, possible breaking changes |

### Checking API Version

```bash
# Check OpenAPI schema version
curl http://localhost:5000/openapi.json | jq '.info.version'

# Check which version an endpoint belongs to
curl http://localhost:5000/openapi.json | jq '.paths["/api/chat/query"]'
```

## Endpoint Groups

### Meta (`/api/meta`)
System information and health checks.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check endpoint |
| GET | `/health/detailed` | Detailed health check with version info |

### Auth (`/api/auth`)
Authentication and session management.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/auth/me` | Get current user info |
| POST | `/auth/register` | User registration |
| POST | `/auth/login` | User login |
| POST | `/auth/logout` | User logout |
| GET | `/auth/tokens` | List API tokens |
| POST | `/auth/tokens` | Create API token |
| POST | `/auth/tokens/{token_id}/revoke` | Revoke an API token |

### Read (`/api/read`)
Document and file reading operations.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/stats` | System statistics |
| GET | `/sources` | List all sources |
| GET | `/categories` | List categories |
| GET | `/files` | List all files |
| GET | `/files/detail` | Get file details |
| GET | `/files/{file_url:path}/markdown` | Get file as markdown |

### Ops-Read (`/api/ops-read`)
Administrative read operations.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/config/sites` | Get site configuration |
| GET | `/schedule/status` | Scheduler status |
| GET | `/scheduled-tasks` | List scheduled tasks |
| GET | `/tasks/active` | List active tasks |
| GET | `/tasks/history` | List task history |
| GET | `/tasks/log/{task_id}` | Get task log |
| GET | `/logs/global` | Global logs |
| GET | `/config/backend-settings` | Backend settings |
| GET | `/config/llm-providers` | LLM provider info |
| GET | `/config/providers` | All providers |
| GET | `/config/provider-credentials` | Provider credentials |
| GET | `/config/model-catalog` | Model catalog |
| GET | `/config/ai-routing` | AI routing config |
| GET | `/config/ai-models` | AI models config |
| GET | `/config/search-engines` | Search engine config |
| GET | `/config/categories` | Categories config |
| GET | `/search` | Search endpoint |

### Ops-Write (`/api/ops-write`)
Administrative write operations.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/config/sites/add` | Add site configuration |
| POST | `/config/sites/update` | Update site configuration |
| POST | `/config/sites/delete` | Delete site configuration |
| POST | `/config/sites/import` | Import sites |
| GET | `/config/sites/export` | Export sites |
| GET | `/config/sites/sample` | Sample site config |
| POST | `/config/backups` | Create backup |
| POST | `/config/backups/restore` | Restore from backup |
| POST | `/config/backups/delete` | Delete backup |
| POST | `/config/backend-settings` | Update backend settings |
| POST | `/config/categories` | Manage categories |
| POST | `/config/ai-models` | Manage AI models |
| POST | `/config/provider-credentials` | Manage provider credentials |
| POST | `/config/provider-credentials/import-env` | Import from env |
| POST | `/config/provider-credentials/re-encrypt` | Re-encrypt credentials |
| DELETE | `/config/provider-credentials/{provider_id}` | Delete provider |
| POST | `/config/ai-routing` | Update AI routing |
| POST | `/scheduled-tasks/add` | Add scheduled task |
| POST | `/scheduled-tasks/update` | Update scheduled task |
| POST | `/scheduled-tasks/delete` | Delete scheduled task |
| POST | `/schedule/reinit` | Reinitialize scheduler |
| POST | `/tasks/stop/{task_id}` | Stop a task |
| POST | `/collections/run` | Trigger on-demand collection |
| GET | `/utils/browse-folder` | Browse folder |
| GET | `/catalog/stats` | Catalog statistics |
| GET | `/markdown_conversion/stats` | Markdown conversion stats |
| GET | `/chunk_generation/stats` | Chunk generation stats |

### Files-Write (`/api/files-write`)
File upload and management.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/files/update` | Upload/update a file |
| POST | `/files/delete` | Delete a file |
| POST | `/files/{file_url:path}/markdown` | Get file as markdown |
| GET | `/download` | Download file |
| GET | `/export` | Export files |
| GET | `/rag/files/preview` | Preview RAG file |
| GET | `/files/{file_url:path}/chunk-sets` | Get chunk sets |
| POST | `/files/{file_url:path}/chunk-sets/generate` | Generate chunk sets |

### RAG-Admin (`/api/rag-admin`)
RAG (Retrieval-Augmented Generation) administration.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/chunk/profiles` | List chunk profiles |
| POST | `/chunk/profiles` | Create chunk profile |
| PUT | `/chunk/profiles/{profile_id}` | Update chunk profile |
| DELETE | `/chunk/profiles/{profile_id}` | Delete chunk profile |
| POST | `/chunk-sets/cleanup` | Cleanup chunk sets |
| GET | `/rag/knowledge-bases` | List knowledge bases |
| POST | `/rag/knowledge-bases` | Create knowledge base |
| GET | `/rag/knowledge-bases/{kb_id}` | Get knowledge base |
| PUT | `/rag/knowledge-bases/{kb_id}` | Update knowledge base |
| DELETE | `/rag/knowledge-bases/{kb_id}` | Delete knowledge base |
| GET | `/rag/knowledge-bases/{kb_id}/stats` | KB statistics |
| GET | `/rag/knowledge-bases/{kb_id}/files` | List KB files |
| POST | `/rag/knowledge-bases/{kb_id}/files` | Add file to KB |
| DELETE | `/rag/knowledge-bases/{kb_id}/files/{file_url:path}` | Remove file from KB |
| GET | `/rag/categories/unmapped` | Unmapped categories |
| GET | `/rag/categories/mapping` | Category mapping |
| GET | `/rag/files/selectable` | Selectable files |
| GET | `/rag/knowledge-bases/{kb_id}/categories` | KB categories |
| POST | `/rag/knowledge-bases/{kb_id}/categories` | Set KB categories |
| GET | `/rag/knowledge-bases/{kb_id}/files/pending` | Pending files |
| POST | `/rag/knowledge-bases/{kb_id}/bindings` | Manage bindings |
| GET | `/rag/knowledge-bases/{kb_id}/bindings` | Get bindings |
| POST | `/rag/knowledge-bases/{kb_id}/index` | Index knowledge base |

### Chat (`/api/chat`)
Chatbot and AI interaction endpoints.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/chat/conversations` | List conversations |
| POST | `/chat/conversations` | Create conversation |
| GET | `/chat/conversations/{conversation_id}` | Get conversation |
| DELETE | `/chat/conversations/{conversation_id}` | Delete conversation |
| GET | `/chat/knowledge-bases` | List available knowledge bases |
| GET | `/chat/available-documents` | List available documents |
| POST | `/chat/query` | Send a chat query |

### Migration (`/api/migration`)
Flask-to-FastAPI migration utilities.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/migration/status` | Migration status |
| GET | `/migration/inventory` | Migration inventory |

## OpenAPI Schema Components

### Common Responses

```yaml
401 Unauthorized:
  description: Authentication required
  content:
    application/json:
      schema:
        type: object
        properties:
          detail:
            type: string
            example: "Authentication required"

403 Forbidden:
  description: Insufficient permissions
  content:
    application/json:
      schema:
        type: object
        properties:
          detail:
            type: string
            example: "Insufficient permissions"

429 Too Many Requests:
  description: Rate limit exceeded
  content:
    application/json:
      schema:
        type: object
        properties:
          detail:
            type: string
            example: "Rate limit exceeded"
```

### Pagination

List endpoints use offset/limit pagination:

```yaml
parameters:
  - in: query
    name: offset
    schema:
      type: integer
      default: 0
      minimum: 0
    description: Number of records to skip before returning results.
  - in: query
    name: limit
    schema:
      type: integer
      default: 20
      minimum: 1
      maximum: 100
    description: Maximum number of records to return.
```

## Documentation Maintenance

- Update this document when adding/removing endpoints
- Keep API examples tested and working
- Document new error codes as they are added
