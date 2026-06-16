# Phase 2.1: AI Chatbot Architecture Design

**Date**: 2026-02-12  
**Phase**: AI Chatbot - Architecture Design  
**Status**: Planning Complete  
**Dependencies**: Phase 1 RAG Core (Complete)

---

## Executive Summary

This document defines the architecture for an intelligent AI chatbot that leverages the RAG (Retrieval-Augmented Generation) system built in Phase 1. The chatbot will provide flexible query modes, intelligent KB selection, conversation management, and high-quality responses with proper citations.

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web Interface                           │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│  │ Chat Page  │  │ Message    │  │ Conversation│               │
│  │            │  │ Display    │  │ History     │               │
│  └────────────┘  └────────────┘  └────────────┘               │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Chatbot Engine Layer                         │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Query      │  │  Conversation │  │   Response   │         │
│  │   Router     │→ │   Manager     │→ │   Generator  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│         │                  │                   │                │
│         ▼                  ▼                   ▼                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ KB Selector  │  │  Context      │  │   Prompt     │         │
│  │              │  │  Manager      │  │   Engine     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Retrieval Layer                          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Embedding   │→ │  FAISS       │→ │  Citation    │         │
│  │  Generator   │  │  Search      │  │  Generator   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LLM Integration Layer                       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   OpenAI     │  │   Retry      │  │  Streaming   │         │
│  │   API        │  │   Logic      │  │  Response    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Chatbot Personas/Modes

### 2.1 Expert Mode (Default)
**Purpose**: Technical, detailed answers with comprehensive citations

**Characteristics**:
- Full technical depth
- Multiple citations per answer
- Includes technical terminology
- Provides context and background
- Highlights edge cases and exceptions

**System Prompt Template**:
```
You are an expert actuarial assistant with deep knowledge of insurance regulations, 
mathematics, and industry practices. Provide detailed, technical answers with proper 
citations. Always cite your sources using [Source: <file_name>] format.

When answering:
1. Be precise and technically accurate
2. Include relevant formulas, regulations, or standards
3. Cite every major claim or fact
4. Explain technical concepts clearly
5. If uncertain, say "I don't have enough information" rather than guessing
```

**Use Cases**:
- Technical research
- Regulatory compliance checks
- Detailed analysis requests

---

### 2.2 Summary Mode
**Purpose**: Concise, high-level overviews for quick understanding

**Characteristics**:
- Brief bullet points
- Key takeaways only
- Minimal citations (top sources)
- Focus on main ideas
- Avoids technical jargon when possible

**System Prompt Template**:
```
You are a concise actuarial assistant. Provide brief, high-level summaries that 
capture the essential information. Use bullet points when appropriate. Cite only 
the most relevant sources.

When answering:
1. Keep responses under 200 words
2. Use bullet points for clarity
3. Focus on key takeaways
4. Avoid excessive detail
5. Cite 1-2 primary sources maximum
```

**Use Cases**:
- Quick overviews
- Executive summaries
- Initial topic exploration

---

### 2.3 Tutorial Mode
**Purpose**: Step-by-step educational explanations

**Characteristics**:
- Structured learning approach
- Progressive disclosure of complexity
- Examples and illustrations
- Checks for understanding
- Building block approach

**System Prompt Template**:
```
You are a patient actuarial tutor. Explain concepts step-by-step as if teaching 
someone new to the topic. Use examples, analogies, and clear progression from 
basic to advanced concepts.

When answering:
1. Start with fundamentals
2. Break complex topics into steps
3. Use examples and analogies
4. Define technical terms
5. Build understanding progressively
6. Cite sources for further reading
```

**Use Cases**:
- Learning new concepts
- Training materials
- Concept clarification

---

### 2.4 Comparison Mode
**Purpose**: Analyze similarities and differences between topics

**Characteristics**:
- Side-by-side analysis
- Highlights similarities and differences
- Structured comparison tables
- Context for differences
- Citations for each side

**System Prompt Template**:
```
You are an analytical actuarial assistant specialized in comparisons. When comparing 
topics, create structured side-by-side analyses highlighting similarities, differences, 
advantages, and disadvantages. Cite sources for each comparison point.

When answering:
1. Use comparison tables or structured lists
2. Identify key similarities
3. Highlight important differences
4. Provide context for differences
5. Include pros/cons when relevant
6. Cite sources for each side
```

**Use Cases**:
- Product comparisons
- Regulation changes over time
- Method comparisons

---

## 3. Knowledge Base Selection Logic

### 3.1 Automatic Selection (Intelligent Routing)

**Algorithm**:
```
1. Analyze query keywords and entities
2. Calculate relevance score for each KB:
   score = keyword_match + entity_match + category_match
3. If top_score > threshold (0.7):
   - Use top KB
4. Else if top 2-3 scores are close (within 0.2):
   - Query multiple KBs
5. Else:
   - Use default KB or ask user
```

**Implementation**:
```python
class KBSelector:
    def select_kb(self, query: str, available_kbs: List[KB]) -> List[str]:
        # Extract query features
        keywords = self._extract_keywords(query)
        entities = self._extract_entities(query)
        
        # Score each KB
        scores = {}
        for kb in available_kbs:
            scores[kb.id] = self._calculate_relevance(
                kb, keywords, entities
            )
        
        # Select KB(s) based on scores
        return self._select_by_scores(scores)
```

---

### 3.2 Manual Selection

**UI Controls**:
- Dropdown: "Select Knowledge Base"
  - Option: "Auto (Recommended)"
  - Option: "All Knowledge Bases"
  - Options: Individual KB names
- Multi-select: For querying multiple specific KBs

**Backend Handling**:
```python
if kb_selection == "auto":
    kb_ids = kb_selector.select_kb(query, available_kbs)
elif kb_selection == "all":
    kb_ids = [kb.id for kb in available_kbs]
elif isinstance(kb_selection, list):
    kb_ids = kb_selection
else:
    kb_ids = [kb_selection]
```

---

### 3.3 Multi-KB Query Support (HIGH PRIORITY)

**Features**:
1. **Query multiple KBs simultaneously**
2. **Merge and rank results** from all KBs
3. **Color-coded citations** (e.g., KB1 in blue, KB2 in green)
4. **Source diversity** (ensure results from each KB)
5. **Conflict detection** (flag contradictory information)

**Merging Algorithm**:
```python
def merge_multi_kb_results(results_by_kb: Dict[str, List[Chunk]]) -> List[Chunk]:
    """
    Merge results from multiple KBs with diversity enforcement.
    """
    # 1. Deduplicate by content similarity
    unique_chunks = deduplicate_chunks(all_chunks)
    
    # 2. Re-rank with diversity bonus
    ranked_chunks = rank_with_diversity(
        unique_chunks, 
        kb_sources=results_by_kb.keys()
    )
    
    # 3. Ensure minimum representation from each KB
    balanced_chunks = ensure_kb_diversity(ranked_chunks, min_per_kb=2)
    
    return balanced_chunks[:top_k]
```

**Citation Format**:
- Single KB: `[Source: regulation_2023.pdf]`
- Multi KB: `[Source: regulation_2023.pdf (General KB)]` with color badge

---

## 4. Conversation Management

### 4.1 Database Schema

**Table: conversations**
```sql
CREATE TABLE conversations (
    conversation_id TEXT PRIMARY KEY,
    user_id TEXT,
    title TEXT,  -- Auto-generated from first query
    kb_id TEXT,  -- Primary KB used
    mode TEXT,   -- Chatbot mode (expert, summary, etc.)
    created_at TEXT,
    updated_at TEXT,
    message_count INTEGER DEFAULT 0,
    metadata TEXT  -- JSON: {kb_ids: [...], settings: {...}}
);
```

**Table: messages**
```sql
CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT,
    role TEXT,  -- 'user' or 'assistant'
    content TEXT,
    citations TEXT,  -- JSON array: [{file: ..., kb: ..., score: ...}]
    created_at TEXT,
    token_count INTEGER,
    metadata TEXT  -- JSON: {model: ..., mode: ..., retrieval_time: ...}
);
```

---

### 4.2 Context Window Management

**Strategy**: Sliding window with intelligent summarization

**Parameters**:
- `max_messages`: 20 (last 10 user + 10 assistant)
- `max_tokens`: 8000 (for GPT-4 context)
- `summarization_threshold`: 15 messages

**Algorithm**:
```
1. If message_count < max_messages:
   - Include all messages in context
2. Else if message_count < summarization_threshold:
   - Include last N messages that fit in max_tokens
3. Else:
   - Summarize messages 1-(N-10) into brief summary
   - Include full messages (N-10) to N
   - Prepend summary to context
```

**Implementation**:
```python
class ContextManager:
    def build_context(self, conversation_id: str) -> List[Message]:
        messages = self._get_messages(conversation_id)
        
        if len(messages) <= self.max_messages:
            return messages
        
        # Need to trim/summarize
        recent_messages = messages[-10:]  # Keep last 10 full
        old_messages = messages[:-10]     # Summarize older ones
        
        summary = self._summarize_messages(old_messages)
        
        return [summary] + recent_messages
```

---

### 4.3 Conversation Title Generation

**Strategy**: Auto-generate from first user query

**Algorithm**:
```
1. Take first user message
2. Extract key topic (GPT-4 mini call)
3. Limit to 50 characters
4. Format: "{topic} - {date}"
```

**Example**:
- Query: "What are the capital requirements for life insurance under Solvency II?"
- Title: "Solvency II Capital Requirements - Feb 12"

---

## 5. Query Processing Pipeline

### 5.1 Query Flow

```
User Query
    │
    ▼
┌─────────────────┐
│ Query Router    │ - Analyze intent
│                 │ - Select KB(s)
│                 │ - Choose mode
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ RAG Retrieval   │ - Generate embedding
│                 │ - Search FAISS index
│                 │ - Filter by threshold
│                 │ - Rank results
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Context Builder │ - Format retrieved chunks
│                 │ - Add conversation history
│                 │ - Build system prompt
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ LLM Generation  │ - Call OpenAI API
│                 │ - Stream response
│                 │ - Handle errors
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Response Post-  │ - Parse citations
│ Processing      │ - Quality check
│                 │ - Format output
└────────┬────────┘
         │
         ▼
    Response to User
```

---

### 5.2 Query Analysis

**Intent Classification**:
- `factual`: Specific fact lookup (e.g., "What is the capital requirement?")
- `explanatory`: Needs explanation (e.g., "How does X work?")
- `comparative`: Comparing items (e.g., "What's the difference between X and Y?")
- `procedural`: Step-by-step process (e.g., "How do I calculate X?")
- `exploratory`: Open-ended exploration (e.g., "Tell me about X")

**Entity Extraction**:
- Regulations (e.g., "Solvency II", "IFRS 17")
- Products (e.g., "term life insurance")
- Concepts (e.g., "risk-based capital")
- Dates/periods (e.g., "2023", "Q4")

**KB Relevance Scoring**:
```python
def calculate_kb_relevance(kb: KnowledgeBase, query_features: dict) -> float:
    """Calculate how relevant a KB is to the query."""
    score = 0.0
    
    # Keyword matching (40%)
    keyword_score = len(set(kb.keywords) & set(query_features['keywords'])) / max(1, len(query_features['keywords']))
    score += 0.4 * keyword_score
    
    # Category matching (30%)
    category_score = 1.0 if kb.category in query_features['categories'] else 0.0
    score += 0.3 * category_score
    
    # Entity matching (30%)
    entity_score = len(set(kb.entities) & set(query_features['entities'])) / max(1, len(query_features['entities']))
    score += 0.3 * entity_score
    
    return score
```

---

## 6. Prompt Engineering

### 6.1 System Prompt Structure

```
[PERSONA INSTRUCTIONS]
<mode-specific instructions>

[CONTEXT]
Retrieved information from knowledge base:

{retrieved_chunks}

[CONVERSATION HISTORY]
{recent_messages}

[TASK REQUIREMENTS]
1. Answer based ONLY on the provided context
2. Cite sources for every major claim using [Source: filename]
3. If information is insufficient, say "I don't have enough information"
4. Do NOT make up or hallucinate information
5. Maintain the specified tone and mode

[QUALITY STANDARDS]
- Accuracy: >95% (verify all facts)
- Citations: Required for all claims
- Relevance: Directly address the query
- Clarity: Clear and understandable
```

---

### 6.2 Citation Format

**In Retrieved Context**:
```
[Document 1] (filename: regulation_2023.pdf, kb: General, score: 0.89)
The capital requirement for life insurance is defined as...

[Document 2] (filename: guide_solvency.pdf, kb: Technical, score: 0.85)
Solvency II requires a risk-based approach...
```

**In LLM Response**:
```
The capital requirement is defined by Solvency II [Source: regulation_2023.pdf] 
and follows a risk-based approach [Source: guide_solvency.pdf].
```

---

### 6.3 Hallucination Prevention

**Strategies**:
1. **Strict prompt instructions**: "Answer ONLY based on provided context"
2. **Confidence thresholds**: Require similarity > 0.4
3. **Citation enforcement**: "Every claim must have a citation"
4. **"I don't know" responses**: Encourage admitting uncertainty
5. **Post-generation validation**: Check citations exist in retrieved chunks

**Validation Algorithm**:
```python
def validate_response(response: str, retrieved_chunks: List[Chunk]) -> dict:
    """Validate response quality and citations."""
    issues = []
    
    # Extract citations from response
    citations = extract_citations(response)
    
    # Check each citation exists in retrieved chunks
    for citation in citations:
        if not any(citation in chunk.metadata['filename'] for chunk in retrieved_chunks):
            issues.append(f"Invalid citation: {citation}")
    
    # Check for hedging phrases (good)
    if has_uncertainty_phrases(response):
        confidence = "medium"
    else:
        confidence = "high"
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "confidence": confidence
    }
```

---

## 7. Error Handling & Edge Cases

### 7.1 No Results from RAG

**Scenario**: Query returns no results above similarity threshold

**Response Strategy**:
```
"I couldn't find specific information about {topic} in the knowledge base. 
This might be because:
1. The information is not in the indexed documents
2. The query needs to be rephrased
3. A different knowledge base might be more appropriate

Would you like to:
- Try rephrasing your question?
- Search a different knowledge base?
- Browse available documents?"
```

---

### 7.2 Contradictory Information (Multi-KB)

**Scenario**: Different KBs provide conflicting information

**Response Strategy**:
```
"I found potentially contradictory information:

From General KB [Source: regulation_2023.pdf]:
- {information A}

From Technical KB [Source: guide_old.pdf]:
- {information B}

This difference might be due to:
- Different time periods (regulation changes)
- Different jurisdictions
- Different interpretation contexts

I recommend: {suggested action}"
```

---

### 7.3 API Errors

**Error Types & Handling**:
1. **Rate Limit**: Exponential backoff, max 5 retries
2. **Timeout**: Retry once, then fail gracefully
3. **Authentication**: Check API key, return configuration error
4. **Model Unavailable**: Fall back to GPT-3.5-turbo

**User-Facing Message**:
```
"I'm experiencing technical difficulties. Please try again in a moment. 
If the problem persists, please contact support."
```

---

## 8. Performance Targets

### 8.1 Latency Targets

| Operation | Target | Max Acceptable |
|-----------|--------|----------------|
| Query → Retrieval | <500ms | 1s |
| Retrieval → LLM Call | <100ms | 200ms |
| LLM Generation | <1.5s | 3s |
| **Total Query Latency** | **<2s** | **4s** |

---

### 8.2 Quality Targets

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Citation Accuracy | >90% | Spot checks |
| Hallucination Rate | <5% | Validation checks |
| User Satisfaction | >80% | User feedback |
| Query Success Rate | >95% | Logs analysis |

---

## 9. Implementation Priorities

### 9.1 MVP (Minimum Viable Product)

**Phase 2.2 - Core Engine**:
1. ✅ Basic query → RAG retrieval → LLM → response
2. ✅ Expert mode only (detailed, technical)
3. ✅ Manual KB selection
4. ✅ Simple conversation history (in-memory)
5. ✅ Basic citation generation

**Phase 2.3 - Web Interface**:
1. ✅ Chat page with message display
2. ✅ KB selector dropdown
3. ✅ Conversation persistence (database)
4. ✅ Citation links to files

---

### 9.2 Enhanced Features (Post-MVP)

**Phase 2.4 - Advanced Features**:
1. 🔥 Multi-KB query (HIGH PRIORITY)
2. 🔥 Automatic KB selection
3. Multiple chatbot modes
4. Semantic query analysis
5. Response quality checks
6. Follow-up suggestions

---

## 10. API Design

### 10.1 Backend Endpoints

**POST /api/chat/query**
```json
Request:
{
  "conversation_id": "conv_123" | null,  // null for new conversation
  "message": "What is the capital requirement?",
  "kb_ids": ["kb1", "kb2"] | "auto" | null,  // null = default KB
  "mode": "expert" | "summary" | "tutorial" | "comparison",
  "stream": false
}

Response:
{
  "conversation_id": "conv_123",
  "message_id": "msg_456",
  "response": "The capital requirement is defined...",
  "citations": [
    {
      "filename": "regulation_2023.pdf",
      "kb_id": "kb1",
      "kb_name": "General",
      "chunk_id": "chunk_789",
      "similarity_score": 0.89
    }
  ],
  "metadata": {
    "retrieval_time_ms": 450,
    "generation_time_ms": 1200,
    "model": "gpt-4",
    "mode": "expert"
  }
}
```

**GET /api/chat/conversations**
```json
Response:
{
  "conversations": [
    {
      "conversation_id": "conv_123",
      "title": "Solvency II Questions",
      "message_count": 5,
      "created_at": "2026-02-12T10:30:00Z",
      "updated_at": "2026-02-12T11:00:00Z"
    }
  ]
}
```

**GET /api/chat/conversations/{conv_id}**
```json
Response:
{
  "conversation_id": "conv_123",
  "title": "Solvency II Questions",
  "kb_id": "kb1",
  "mode": "expert",
  "messages": [
    {
      "message_id": "msg_1",
      "role": "user",
      "content": "What is Solvency II?",
      "created_at": "2026-02-12T10:30:00Z"
    },
    {
      "message_id": "msg_2",
      "role": "assistant",
      "content": "Solvency II is a European Union...",
      "citations": [...],
      "created_at": "2026-02-12T10:30:05Z"
    }
  ]
}
```

---

## 11. Security & Privacy

### 11.1 Authentication

- All chat endpoints require authentication (same as RAG endpoints)
- Use existing `CONFIG_WRITE_AUTH_TOKEN` for write operations
- Session-based auth for UI (login required)

### 11.2 Data Privacy

- Conversations are user-specific (filtered by `user_id`)
- API keys stored securely (environment variables)
- No logging of actual query content (only metadata)
- Option to delete conversations and messages

---

## 12. Next Steps

### Phase 2.2 Implementation Order:

1. **Module Structure** (Day 1)
   - Create `ai_actuarial/chatbot/` directory
   - Setup `__init__.py`, `config.py`, `exceptions.py`

2. **RAG Retrieval Integration** (Day 1-2)
   - Implement `retrieval.py` with KB query support
   - Add citation generation

3. **LLM Integration** (Day 2-3)
   - Implement `llm.py` with OpenAI GPT-4
   - Add retry logic and error handling

4. **Prompt Engineering** (Day 3)
   - Create `prompts.py` with system prompts
   - Implement context formatting

5. **Conversation Manager** (Day 4)
   - Implement `conversation.py`
   - Add database persistence

6. **Query Router** (Day 5)
   - Implement `router.py` for KB selection
   - Add query analysis

---

## 13. Testing Strategy

### 13.1 Unit Tests

- Test each component in isolation
- Mock external dependencies (OpenAI API, database)
- Cover edge cases (empty results, errors, etc.)

### 13.2 Integration Tests

- Test full query flow end-to-end
- Test with real RAG system (test KB)
- Test conversation persistence

### 13.3 Performance Tests

- Measure latency for different query types
- Test with concurrent requests
- Profile memory usage

---

## 14. Success Criteria

### Phase 2.1 (Architecture) ✅
- [x] Architecture document complete
- [x] All design decisions documented
- [x] APIs defined
- [x] Implementation priorities set

### Phase 2.2 (Core Engine)
- [ ] Query → RAG retrieval → LLM → response works
- [ ] Citation generation accurate
- [ ] Error handling robust
- [ ] Unit tests pass
- [ ] Latency <2s for 80% of queries

### Phase 2.3 (Web Interface)
- [ ] Chat page functional
- [ ] Conversation persistence working
- [ ] Citation links work
- [ ] UI responsive and intuitive

---

## Appendix A: Configuration Parameters

```python
# config.py example
@dataclass
class ChatbotConfig:
    # LLM Settings
    llm_provider: str = "openai"  # openai, anthropic, ollama
    model: str = "gpt-4"  # gpt-4, gpt-4-turbo, gpt-3.5-turbo
    temperature: float = 0.7
    max_tokens: int = 1000
    
    # Retrieval Settings
    top_k: int = 5  # Number of chunks to retrieve
    similarity_threshold: float = 0.4
    
    # Conversation Settings
    max_messages: int = 20
    max_context_tokens: int = 8000
    summarization_threshold: int = 15
    
    # Mode Settings
    default_mode: str = "expert"
    available_modes: List[str] = field(default_factory=lambda: [
        "expert", "summary", "tutorial", "comparison"
    ])
    
    # Retry & Rate Limiting
    max_retries: int = 3
    retry_delay: float = 1.0  # seconds
    rate_limit_rpm: int = 60  # requests per minute
```

---

## Appendix B: Error Codes

| Code | Error | Description |
|------|-------|-------------|
| CB001 | InvalidKB | KB ID not found or invalid |
| CB002 | NoResults | No retrieval results above threshold |
| CB003 | LLMError | Error calling LLM API |
| CB004 | InvalidMode | Unsupported chatbot mode |
| CB005 | ConversationNotFound | Conversation ID not found |
| CB006 | RateLimitExceeded | Too many requests |
| CB007 | InvalidCitation | Citation validation failed |

---

**End of Architecture Design Document**
