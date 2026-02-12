# AI Chatbot API Documentation

**Version**: 1.0  
**Date**: 2026-02-12  
**Base URL**: `/api/chat`

---

## Overview

The Chatbot API provides endpoints for querying knowledge bases with an AI assistant, managing conversations, and retrieving conversation history.

### Authentication

All endpoints require authentication using one of:
- **Session-based**: Login via web interface
- **Token-based**: `Authorization: Bearer <token>` header

### Rate Limiting

- **60 requests per minute** per user
- **429 Too Many Requests** response if exceeded
- Retry after header indicates wait time

---

## Endpoints

### 1. Query Chatbot

Submit a query to the AI chatbot and receive a response.

**Endpoint**: `POST /api/chat/query`

**Request Body**:
```json
{
  "conversation_id": "conv_123abc",  // Optional: null for new conversation
  "message": "What are the capital requirements?",  // Required
  "kb_ids": ["kb1", "kb2"],  // Optional: ["auto"] | ["all"] | [kb_ids] | null
  "mode": "expert",  // Optional: "expert" | "summary" | "tutorial" | "comparison"
  "stream": false  // Optional: streaming not yet implemented
}
```

**Response** (200 OK):
```json
{
  "conversation_id": "conv_123abc",
  "message_id": "msg_456def",
  "response": "The capital requirements are defined as...",
  "citations": [
    {
      "filename": "regulation_2023.pdf",
      "file_url": "/files/reg/regulation_2023.pdf",
      "kb_id": "kb1",
      "kb_name": "General Knowledge Base",
      "chunk_id": "chunk_789ghi",
      "similarity_score": 0.89
    }
  ],
  "metadata": {
    "retrieval_time_ms": 450,
    "generation_time_ms": 1200,
    "total_time_ms": 1650,
    "model": "gpt-4",
    "mode": "expert",
    "kb_ids_used": ["kb1"],
    "chunk_count": 5
  }
}
```

**Error Responses**:
- `400 Bad Request`: Missing required fields, invalid mode
- `401 Unauthorized`: Authentication required
- `404 Not Found`: KB not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: OpenAI API unavailable

**Example**:
```bash
curl -X POST http://localhost:5000/api/chat/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "What is Solvency II?",
    "kb_ids": ["auto"],
    "mode": "summary"
  }'
```

---

### 2. List Conversations

Retrieve all conversations for the authenticated user.

**Endpoint**: `GET /api/chat/conversations`

**Query Parameters**:
- `limit` (optional): Maximum conversations to return (default: 50, max: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response** (200 OK):
```json
{
  "conversations": [
    {
      "conversation_id": "conv_123abc",
      "title": "Solvency II Questions - Feb 12",
      "kb_id": "kb1",
      "mode": "expert",
      "message_count": 5,
      "created_at": "2026-02-12T10:30:00Z",
      "updated_at": "2026-02-12T11:00:00Z"
    },
    {
      "conversation_id": "conv_456def",
      "title": "Risk Assessment Guide - Feb 11",
      "kb_id": "kb2",
      "mode": "tutorial",
      "message_count": 12,
      "created_at": "2026-02-11T14:00:00Z",
      "updated_at": "2026-02-11T15:30:00Z"
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

**Example**:
```bash
curl http://localhost:5000/api/chat/conversations \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 3. Get Conversation

Retrieve full conversation history including all messages.

**Endpoint**: `GET /api/chat/conversations/<conversation_id>`

**Response** (200 OK):
```json
{
  "conversation_id": "conv_123abc",
  "title": "Solvency II Questions - Feb 12",
  "user_id": "user_001",
  "kb_id": "kb1",
  "mode": "expert",
  "created_at": "2026-02-12T10:30:00Z",
  "updated_at": "2026-02-12T11:00:00Z",
  "message_count": 4,
  "messages": [
    {
      "message_id": "msg_1",
      "role": "user",
      "content": "What is Solvency II?",
      "citations": null,
      "created_at": "2026-02-12T10:30:00Z",
      "token_count": 5
    },
    {
      "message_id": "msg_2",
      "role": "assistant",
      "content": "Solvency II is a European Union directive...",
      "citations": [
        {
          "filename": "solvency_ii_guide.pdf",
          "file_url": "/files/guides/solvency_ii_guide.pdf",
          "kb_id": "kb1",
          "similarity_score": 0.92
        }
      ],
      "created_at": "2026-02-12T10:30:05Z",
      "token_count": 150
    }
  ]
}
```

**Error Responses**:
- `401 Unauthorized`: Not authenticated
- `403 Forbidden`: Not your conversation
- `404 Not Found`: Conversation not found

**Example**:
```bash
curl http://localhost:5000/api/chat/conversations/conv_123abc \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 4. Create Conversation

Create a new conversation with specified settings.

**Endpoint**: `POST /api/chat/conversations`

**Request Body**:
```json
{
  "kb_id": "kb1",  // Optional: default KB
  "mode": "expert",  // Optional: default mode
  "title": "My Custom Title"  // Optional: auto-generated if not provided
}
```

**Response** (201 Created):
```json
{
  "conversation_id": "conv_789ghi",
  "title": "New Conversation - Feb 12",
  "kb_id": "kb1",
  "mode": "expert",
  "created_at": "2026-02-12T12:00:00Z"
}
```

**Example**:
```bash
curl -X POST http://localhost:5000/api/chat/conversations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "kb_id": "kb1",
    "mode": "summary"
  }'
```

---

### 5. Delete Conversation

Delete a conversation and all its messages.

**Endpoint**: `DELETE /api/chat/conversations/<conversation_id>`

**Response** (200 OK):
```json
{
  "message": "Conversation deleted successfully",
  "conversation_id": "conv_123abc"
}
```

**Error Responses**:
- `401 Unauthorized`: Not authenticated
- `403 Forbidden`: Not your conversation
- `404 Not Found`: Conversation not found

**Example**:
```bash
curl -X DELETE http://localhost:5000/api/chat/conversations/conv_123abc \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 6. List Knowledge Bases

Get list of available knowledge bases for chatbot queries.

**Endpoint**: `GET /api/chat/knowledge-bases`

**Response** (200 OK):
```json
{
  "knowledge_bases": [
    {
      "id": "kb1",
      "name": "General Regulations",
      "description": "General actuarial regulations and guidelines",
      "file_count": 150,
      "chunk_count": 3200,
      "created_at": "2026-01-15T10:00:00Z",
      "updated_at": "2026-02-10T15:30:00Z"
    },
    {
      "id": "kb2",
      "name": "Technical Documentation",
      "description": "Technical guides and specifications",
      "file_count": 87,
      "chunk_count": 1950,
      "created_at": "2026-01-20T14:00:00Z",
      "updated_at": "2026-02-11T09:15:00Z"
    }
  ],
  "total": 2
}
```

**Example**:
```bash
curl http://localhost:5000/api/chat/knowledge-bases \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Data Models

### Conversation Object

```typescript
interface Conversation {
  conversation_id: string;      // Unique identifier
  user_id: string;              // Owner user ID
  title: string;                // Conversation title
  kb_id: string;                // Primary knowledge base ID
  mode: string;                 // Chatbot mode
  created_at: string;           // ISO 8601 timestamp
  updated_at: string;           // ISO 8601 timestamp
  message_count: number;        // Total messages
  metadata?: object;            // Additional metadata
}
```

### Message Object

```typescript
interface Message {
  message_id: string;           // Unique identifier
  conversation_id: string;      // Parent conversation
  role: "user" | "assistant";   // Message role
  content: string;              // Message text
  citations: Citation[] | null; // Sources (assistant only)
  created_at: string;           // ISO 8601 timestamp
  token_count: number;          // Token count
  metadata?: object;            // Additional metadata
}
```

### Citation Object

```typescript
interface Citation {
  filename: string;             // Source filename
  file_url: string;             // URL to file detail page
  kb_id: string;                // Knowledge base ID
  kb_name?: string;             // Knowledge base name
  chunk_id: string;             // Chunk identifier
  similarity_score: number;     // Relevance score (0-1)
}
```

---

## Chatbot Modes

The `mode` parameter controls the chatbot's response style:

| Mode | Description | Response Style | Best For |
|------|-------------|----------------|----------|
| `expert` | Detailed, technical | Comprehensive with full citations | Research, technical analysis |
| `summary` | Concise overview | Brief bullet points | Quick info, time-constrained |
| `tutorial` | Educational | Step-by-step, examples | Learning, training |
| `comparison` | Analytical | Side-by-side comparison | Comparing options, analysis |

---

## Knowledge Base Selection

The `kb_ids` parameter supports:

| Value | Behavior | Use Case |
|-------|----------|----------|
| `null` or omitted | Use default KB | Standard queries |
| `["auto"]` | Auto-select best KB | General queries, unsure which KB |
| `["all"]` | Query all KBs | Comprehensive research |
| `["kb1"]` | Query specific KB | Targeted search |
| `["kb1", "kb2"]` | Query multiple KBs | Cross-reference sources |

---

## Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `CB001` | 400 | Invalid KB ID |
| `CB002` | 404 | No retrieval results found |
| `CB003` | 503 | LLM API error |
| `CB004` | 400 | Invalid chatbot mode |
| `CB005` | 404 | Conversation not found |
| `CB006` | 429 | Rate limit exceeded |
| `CB007` | 500 | Citation validation failed |

**Error Response Format**:
```json
{
  "error": {
    "code": "CB003",
    "message": "Failed to generate response: OpenAI API timeout",
    "details": "The request timed out after 30 seconds"
  }
}
```

---

## Rate Limiting

**Limits**:
- 60 requests per minute per user
- Applies to `/api/chat/query` endpoint primarily

**Headers**:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1644678900
```

**429 Response**:
```json
{
  "error": {
    "code": "CB006",
    "message": "Rate limit exceeded",
    "retry_after": 30
  }
}
```

---

## Best Practices

### Efficient Querying

1. **Use Specific KBs**: If you know which KB, specify it
2. **Choose Appropriate Mode**: Don't use Expert if Summary sufficient
3. **Reuse Conversations**: Context improves with conversation history
4. **Cache Responses**: Don't re-query for same information

### Error Handling

1. **Implement Retries**: With exponential backoff for 5xx errors
2. **Handle Rate Limits**: Respect 429 responses, wait before retry
3. **Validate Input**: Check mode and KB IDs before sending
4. **Log Errors**: Track patterns for debugging

### Performance

1. **Monitor Latency**: Track `total_time_ms` in metadata
2. **Use Auto KB**: Often faster than "All KBs"
3. **Limit Context**: Don't load massive conversation histories
4. **Pagination**: Use limit/offset for conversation lists

---

## Examples

### Python Client

```python
import requests

class ChatbotClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def query(self, message, conversation_id=None, kb_ids=None, mode="expert"):
        """Send a query to the chatbot."""
        url = f"{self.base_url}/api/chat/query"
        payload = {
            "message": message,
            "conversation_id": conversation_id,
            "kb_ids": kb_ids or ["auto"],
            "mode": mode
        }
        response = requests.post(url, json=payload, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def list_conversations(self, limit=50):
        """List user's conversations."""
        url = f"{self.base_url}/api/chat/conversations"
        params = {"limit": limit}
        response = requests.get(url, params=params, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def get_conversation(self, conversation_id):
        """Get full conversation history."""
        url = f"{self.base_url}/api/chat/conversations/{conversation_id}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

# Usage
client = ChatbotClient("http://localhost:5000", "YOUR_TOKEN")

# Query
result = client.query(
    message="What is Solvency II?",
    kb_ids=["auto"],
    mode="summary"
)
print(result["response"])

# List conversations
conversations = client.list_conversations()
for conv in conversations["conversations"]:
    print(f"{conv['title']} - {conv['message_count']} messages")
```

### JavaScript Client

```javascript
class ChatbotClient {
    constructor(baseUrl, token) {
        this.baseUrl = baseUrl;
        this.headers = {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
    }
    
    async query(message, conversationId = null, kbIds = ['auto'], mode = 'expert') {
        const response = await fetch(`${this.baseUrl}/api/chat/query`, {
            method: 'POST',
            headers: this.headers,
            body: JSON.stringify({
                message,
                conversation_id: conversationId,
                kb_ids: kbIds,
                mode
            })
        });
        
        if (!response.ok) {
            throw new Error(`Query failed: ${response.statusText}`);
        }
        
        return response.json();
    }
    
    async listConversations(limit = 50) {
        const response = await fetch(
            `${this.baseUrl}/api/chat/conversations?limit=${limit}`,
            { headers: this.headers }
        );
        
        if (!response.ok) {
            throw new Error(`List failed: ${response.statusText}`);
        }
        
        return response.json();
    }
    
    async getConversation(conversationId) {
        const response = await fetch(
            `${this.baseUrl}/api/chat/conversations/${conversationId}`,
            { headers: this.headers }
        );
        
        if (!response.ok) {
            throw new Error(`Get failed: ${response.statusText}`);
        }
        
        return response.json();
    }
}

// Usage
const client = new ChatbotClient('http://localhost:5000', 'YOUR_TOKEN');

// Query
const result = await client.query(
    'What is Solvency II?',
    null,
    ['auto'],
    'summary'
);
console.log(result.response);

// List conversations
const conversations = await client.listConversations();
conversations.conversations.forEach(conv => {
    console.log(`${conv.title} - ${conv.message_count} messages`);
});
```

---

## Changelog

### Version 1.0 (2026-02-12)
- Initial release
- 6 API endpoints
- Support for 4 chatbot modes
- Multi-KB query capability
- Conversation management
- Citation generation

---

## Support

**Issues**: Report via GitHub Issues  
**Questions**: Contact development team  
**Updates**: Check this document for API changes

---

**Last Updated**: 2026-02-12  
**Version**: 1.0  
**Status**: Stable

---

**End of API Documentation**
