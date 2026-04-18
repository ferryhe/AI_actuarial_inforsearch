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

### URL Path Versioning (Current → Planned)
The recommended path for explicit versioning when needed:

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
| `POST /api/rag-admin/index` | Indexing strategy evolves with RAG improvements |
| `GET /api/read/inventory` | Pagination and filter schema may expand |
| `POST /api/files-write/upload` | File processing pipeline changes |

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
| GET | `/meta/version` | API version info |

### Auth (`/api/auth`)
Authentication and session management.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | User login |
| POST | `/auth/logout` | User logout |
| GET | `/auth/session` | Get current session |

### Read (`/api/read`)
Document and file reading operations.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/read/inventory` | List all inventory items |
| GET | `/read/inventory/{id}` | Get specific inventory item |
| GET | `/read/search` | Search documents |

### Ops-Read (`/api/ops-read`)
Administrative read operations.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/ops-read/stats` | System statistics |
| GET | `/ops-read/config` | Runtime configuration |

### Ops-Write (`/api/ops-write`)
Administrative write operations.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/ops-write/reload-config` | Reload configuration |

### Files-Write (`/api/files-write`)
File upload and management.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/files-write/upload` | Upload a file |
| DELETE | `/files-write/{id}` | Delete a file |

### RAG-Admin (`/api/rag-admin`)
RAG (Retrieval-Augmented Generation) administration.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/rag-admin/index` | Index a document |
| DELETE | `/rag-admin/index/{id}` | Remove from index |

### Chat (`/api/chat`)
Chatbot and AI interaction endpoints.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/chat/query` | Send a chat query |
| GET | `/chat/history` | Get chat history |

### Migration (`/api/migration`)
Flask-to-FastAPI migration utilities.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/migration/status` | Migration status |
| POST | `/migration/flag` | Set migration flag |

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

List endpoints use cursor-based pagination:

```yaml
PaginationParams:
  in: query
  name: offset
  schema:
    type: integer
    default: 0
    minimum: 0

  in: query
  name: limit
  schema:
    type: integer
    default: 20
    minimum: 1
    maximum: 100
```

## Documentation Maintenance

- Update this document when adding/removing endpoints
- Keep API examples tested and working
- Document new error codes as they are added
