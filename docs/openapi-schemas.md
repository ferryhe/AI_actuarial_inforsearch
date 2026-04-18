# OpenAPI 3.0 Schemas — AI Actuarial Info Search API

> This document documents the **top 5 most critical endpoints** using OpenAPI 3.0 schema notation.
> For the full interactive API reference, visit `/docs` (Swagger UI) or `/redoc` (ReDoc) when the server is running.

---

## Table of Contents

1. [`GET /api/search`](#1-get-apisearch) — Knowledge-base keyword search
2. [`POST /api/collections/run`](#2-post-apicollectionsrun) — Trigger on-demand collection
3. [`GET /api/tasks/active`](#3-get-apitasksactive) — List active tasks
4. [`POST /api/chat/query`](#4-post-apichatquery) — RAG chat query
5. [`GET /api/chat/conversations/{conversation_id}`](#5-get-apichatconversationsconversation_id) — Get conversation history

---

## 1. `GET /api/search`

Search the knowledge-base catalog by keyword.

### Request

```
GET /api/search?q={query}&kb_id={kb_id}&limit={limit}
Authorization: Bearer <token>
```

| Field | In | Type | Required | Description |
|-------|----|------|----------|-------------|
| `q` | query | string | ✅ | Search query (case-insensitive substring match on name + description) |
| `kb_id` | query | string | ❌ | Optional knowledge-base ID to scope results to one category |
| `limit` | query | integer | ❌ | Max results to return, 1–100, default 20 |

### Response `200 OK`

```json
{
  "results": [
    {
      "kb_id": "kb_abc123",
      "name": "SOA Actuarial Standards",
      "description": "Standards and guidance from the Society of Actuaries",
      "created_at": "2025-03-01T10:00:00Z",
      "score": 10
    }
  ],
  "count": 1
}
```

| Field | Type | Description |
|-------|------|-------------|
| `results` | array[object] | List of matching knowledge bases, ordered by descending `score` |
| `results[].kb_id` | string | Unique knowledge-base identifier |
| `results[].name` | string | Human-readable name |
| `results[].description` | string | Description text |
| `results[].created_at` | string (ISO 8601) | When the KB was created |
| `results[].score` | integer | Relevance score (higher = more relevant) |
| `count` | integer | Total matches before pagination limit |

### Error Responses

| Status | Description |
|--------|-------------|
| `401` | Authentication required |
| `403` | Caller lacks `catalog.read` permission |

---

## 2. `POST /api/collections/run`

Trigger an immediate on-demand document collection (crawl + ingestion) for one or more sites.

### Request

```
POST /api/collections/run
Authorization: Bearer <token>
Content-Type: application/json
```

**Request body:**

```json
{
  "name": "soa-publications",
  "force": true,
  "depth": 2,
  "category": "soa"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Site name (must match a configured site in sites.yaml) |
| `force` | boolean | ❌ | If `true`, re-downloads already-processed pages; default `false` |
| `depth` | integer | ❌ | Crawl depth override; omit to use site default |
| `category` | string | ❌ | Category override for this run |

### Response `200 OK`

```json
{
  "task_id": "task_xyz789",
  "status": "queued",
  "site": "soa-publications",
  "started_at": "2026-04-19T06:50:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Unique identifier for the new collection task |
| `status` | string | Initial status: `"queued"` |
| `site` | string | Site name the task is running for |
| `started_at` | string (ISO 8601) | Timestamp the task was enqueued |

### Error Responses

| Status | Description |
|--------|-------------|
| `400` | Payload invalid or site name not found |
| `401` | Authentication required |
| `403` | Caller lacks `tasks.run` permission |
| `409` | A collection for this site is already running |
| `429` | Rate limit exceeded |

---

## 3. `GET /api/tasks/active`

Return all currently in-progress (running) tasks.

### Request

```
GET /api/tasks/active
Authorization: Bearer <token>
```

### Response `200 OK`

```json
{
  "active_tasks": [
    {
      "task_id": "task_xyz789",
      "task_type": "collection",
      "site_name": "soa-publications",
      "status": "running",
      "progress_pct": 45,
      "pages_processed": 120,
      "pages_total": 267,
      "started_at": "2026-04-19T06:50:00Z",
      "estimated_finish": "2026-04-19T07:05:00Z"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `active_tasks` | array[object] | List of currently running tasks |
| `active_tasks[].task_id` | string | Unique task identifier |
| `active_tasks[].task_type` | string | Type: `"collection"`, `"crawl"`, `"index"` etc. |
| `active_tasks[].site_name` | string | Name of the site being collected |
| `active_tasks[].status` | string | Current state: `"running"`, `"paused"`, `"stopping"` |
| `active_tasks[].progress_pct` | integer | Estimated completion percentage (0–100) |
| `active_tasks[].pages_processed` | integer | Number of pages processed so far |
| `active_tasks[].pages_total` | integer | Estimated total pages to process |
| `active_tasks[].started_at` | string (ISO 8601) | When the task started |
| `active_tasks[].estimated_finish` | string (ISO 8601) | Estimated completion time |

### Error Responses

| Status | Description |
|--------|-------------|
| `401` | Authentication required |
| `403` | Caller lacks `tasks.view` permission |

---

## 4. `POST /api/chat/query`

Send a user message to the RAG chatbot and receive a response grounded in the knowledge base.

### Request

```
POST /api/chat/query
Authorization: Bearer <token>
Content-Type: application/json
```

**Request body:**

```json
{
  "conversation_id": "conv_abc123",
  "message": "What are the latest SOA continuing education requirements?",
  "kb_ids": ["kb_soa_main", "kb_soa_ce"],
  "stream": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `conversation_id` | string | ❌ | Existing conversation ID to continue; omit or use `null` to start a new conversation |
| `message` | string | ✅ | User's natural-language question |
| `kb_ids` | array[string] | ❌ | Restrict retrieval to these knowledge-base IDs |
| `stream` | boolean | ❌ | If `true`, response uses server-sent events; default `false` |

### Response `200 OK` (non-streaming)

```json
{
  "conversation_id": "conv_abc123",
  "reply": "Based on the SOA continuing education requirements...",
  "references": [
    {
      "kb_id": "kb_soa_main",
      "kb_name": "SOA Main",
      "doc_title": "CE Requirements 2025",
      "doc_id": "doc_001",
      "chunk_snippet": "...at least 30 hours of CE every two years...",
      "relevance_score": 0.94
    }
  ],
  "model_used": "gpt-4o-mini",
  "tokens_used": 1842,
  "created_at": "2026-04-19T06:55:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `conversation_id` | string | Conversation ID (echoed from request or newly created) |
| `reply` | string | Assistant's full text response |
| `references` | array[object] | Retrieved document chunks used to ground the answer |
| `references[].kb_id` | string | Source knowledge-base ID |
| `references[].kb_name` | string | Source KB display name |
| `references[].doc_title` | string | Title of the source document |
| `references[].doc_id` | string | Internal document identifier |
| `references[].chunk_snippet` | string | Relevant excerpt from the retrieved chunk |
| `references[].relevance_score` | float | Relevance score (0–1) of this chunk |
| `model_used` | string | LLM model that generated the response |
| `tokens_used` | integer | Total tokens consumed for this turn |
| `created_at` | string (ISO 8601) | Timestamp of the response |

### Error Responses

| Status | Description |
|--------|-------------|
| `400` | Malformed payload or missing `message` field |
| `401` | Authentication required |
| `403` | Caller lacks `chat.query` permission |
| `429` | Chat rate limit exceeded |
| `503` | No LLM provider configured or provider unreachable |

---

## 5. `GET /api/chat/conversations/{conversation_id}`

Retrieve the full message history and metadata of a specific conversation.

### Request

```
GET /api/chat/conversations/{conversation_id}
Authorization: Bearer <token>
```

| Field | In | Type | Required | Description |
|-------|----|------|----------|-------------|
| `conversation_id` | path | string | ✅ | The conversation identifier |

### Response `200 OK`

```json
{
  "conversation_id": "conv_abc123",
  "title": "SOA CE Requirements Discussion",
  "created_at": "2026-04-18T09:00:00Z",
  "updated_at": "2026-04-19T06:55:00Z",
  "message_count": 8,
  "messages": [
    {
      "turn_id": 1,
      "role": "user",
      "content": "What are the latest SOA continuing education requirements?",
      "created_at": "2026-04-18T09:01:00Z"
    },
    {
      "turn_id": 2,
      "role": "assistant",
      "content": "Based on the SOA continuing education requirements...",
      "created_at": "2026-04-18T09:01:30Z",
      "tokens_used": 842,
      "references": [
        {
          "kb_id": "kb_soa_main",
          "doc_title": "CE Requirements 2025",
          "chunk_snippet": "...at least 30 hours of CE every two years...",
          "relevance_score": 0.94
        }
      ]
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `conversation_id` | string | Unique conversation identifier |
| `title` | string | Conversation title (auto-generated or user-set) |
| `created_at` | string (ISO 8601) | When the conversation was created |
| `updated_at` | string (ISO 8601) | When the last message was added |
| `message_count` | integer | Total number of messages in the conversation |
| `messages` | array[object] | Ordered list of message turns |
| `messages[].turn_id` | integer | Sequential turn number |
| `messages[].role` | string | `"user"` or `"assistant"` |
| `messages[].content` | string | Message text content |
| `messages[].created_at` | string (ISO 8601) | When the message was created |
| `messages[].tokens_used` | integer | Tokens consumed for assistant turns only |
| `messages[].references` | array[object] | Retrieved grounding documents (assistant turns only) |

### Error Responses

| Status | Description |
|--------|-------------|
| `401` | Authentication required |
| `403` | Caller lacks `chat.conversations` permission |
| `404` | Conversation not found or belongs to another user |

---

## Common Error Schema

All endpoints may return errors in the following format:

```json
{
  "error": "Human-readable error message",
  "detail": "Optional technical detail for debugging"
}
```

| Status | Meaning |
|--------|---------|
| `400` | Bad Request — invalid input |
| `401` | Unauthorized — authentication missing or expired |
| `403` | Forbidden — insufficient permissions |
| `404` | Not Found — resource does not exist |
| `409` | Conflict — resource already exists or state conflict |
| `429` | Too Many Requests — rate limit exceeded |
| `500` | Internal Server Error — unexpected server failure |
| `503` | Service Unavailable — upstream dependency unreachable |
