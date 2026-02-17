# Dynamic AI Model Fetching - Future Implementation Plan

**Date Created**: 2026-02-16  
**Status**: 📋 Planned  
**Priority**: Medium  
**Estimated Effort**: 3-5 days

---

## Overview

Implement dynamic fetching of available AI models from provider APIs instead of maintaining hardcoded model lists. This enhancement will allow the application to automatically discover and display up-to-date model options from AI providers like OpenAI, Mistral, and SiliconFlow.

**Inspiration**: Similar to RAGFlow's implementation where model lists are dynamically pulled from provider APIs.

---

## Current State

### Limitations
- Models are hardcoded in `AI_AVAILABLE_MODELS` dictionary in `ai_actuarial/web/app.py`
- Requires code updates when new models are released
- Cannot adapt to user-specific model availability (e.g., custom fine-tuned models)
- No visibility into model deprecations or new releases

### Current Implementation
```python
AI_AVAILABLE_MODELS = {
    "openai": [
        {"name": "gpt-4-turbo", "display_name": "GPT-4 Turbo", "types": ["chatbot", "catalog"]},
        {"name": "gpt-4o", "display_name": "GPT-4o", "types": ["chatbot", "catalog"]},
        # ... hardcoded list
    ],
    # ... other providers
}
```

**Location**: `ai_actuarial/web/app.py:1400-1423`

---

## Proposed Solution

### Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Web UI (Settings)                  │
│  - Click "Refresh Models" button for each provider  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│     API: /api/config/ai-models/fetch/{provider}     │
│  - Validates API key exists                          │
│  - Calls provider's model list API                   │
│  - Filters & formats results                         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Model Fetcher Service                   │
│  - OpenAIModelFetcher                                │
│  - MistralModelFetcher                               │
│  - SiliconFlowModelFetcher                           │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                  Cache Layer                         │
│  - Redis/In-memory cache (TTL: 1 hour)              │
│  - Fallback to hardcoded list on failure             │
└─────────────────────────────────────────────────────┘
```

### Components

#### 1. Backend API Endpoint

**New File**: `ai_actuarial/web/model_fetcher.py`

```python
class ModelFetcher:
    """Base class for fetching models from AI providers."""
    
    @abstractmethod
    def fetch_models(self, api_key: str) -> List[Dict[str, Any]]:
        """Fetch available models from provider API."""
        pass
    
    @abstractmethod
    def categorize_model(self, model: Dict) -> List[str]:
        """Determine which types (chatbot, catalog, embeddings, ocr) a model supports."""
        pass

class OpenAIModelFetcher(ModelFetcher):
    """Fetch models from OpenAI API."""
    
    def fetch_models(self, api_key: str) -> List[Dict[str, Any]]:
        """
        Calls: GET https://api.openai.com/v1/models
        Filters: Only models the user has access to
        Returns: Formatted list with name, display_name, types
        """
        pass

class MistralModelFetcher(ModelFetcher):
    """Fetch models from Mistral API."""
    pass

class SiliconFlowModelFetcher(ModelFetcher):
    """Fetch models from SiliconFlow API."""
    pass
```

**New Endpoint**: `/api/config/ai-models/fetch/{provider}`

```python
@app.route("/api/config/ai-models/fetch/<provider>")
@require_permissions("config.read")
def api_fetch_ai_models(provider: str):
    """
    Dynamically fetch available models from AI provider.
    
    Args:
        provider: One of 'openai', 'mistral', 'siliconflow'
    
    Query Parameters:
        force_refresh: bool (default: false) - Skip cache
    
    Returns:
        {
            "provider": "openai",
            "models": [
                {
                    "name": "gpt-4-turbo",
                    "display_name": "GPT-4 Turbo",
                    "types": ["chatbot", "catalog"],
                    "context_window": 128000,
                    "created": "2024-04-09"
                },
                ...
            ],
            "cached": true,
            "fetched_at": "2026-02-16T01:00:00Z"
        }
    
    Error Cases:
        - 400: Invalid provider
        - 401: API key not configured
        - 500: API call failed (returns cached/fallback data)
    """
    pass
```

#### 2. Caching Strategy

**Option A: In-Memory Cache** (Simpler, for initial implementation)
```python
from functools import lru_cache
from datetime import datetime, timedelta

_model_cache = {}
CACHE_TTL = timedelta(hours=1)

def get_cached_models(provider: str) -> Optional[Dict]:
    """Get models from cache if not expired."""
    if provider in _model_cache:
        cached_data = _model_cache[provider]
        if datetime.now() - cached_data['timestamp'] < CACHE_TTL:
            return cached_data['models']
    return None
```

**Option B: Redis Cache** (Scalable, for production)
```python
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)
CACHE_TTL_SECONDS = 3600  # 1 hour

def get_cached_models(provider: str) -> Optional[Dict]:
    """Get models from Redis cache."""
    cached = redis_client.get(f"ai_models:{provider}")
    return json.loads(cached) if cached else None

def set_cached_models(provider: str, models: Dict):
    """Cache models in Redis with TTL."""
    redis_client.setex(
        f"ai_models:{provider}",
        CACHE_TTL_SECONDS,
        json.dumps(models)
    )
```

#### 3. Frontend UI Enhancements

**File**: `ai_actuarial/web/templates/settings.html`

Add "Refresh Models" button for each provider:

```html
<div class="provider-section">
    <label>OpenAI Models</label>
    <select id="openai-model-select" class="form-control">
        <!-- Populated dynamically -->
    </select>
    <button class="btn btn-secondary btn-sm" onclick="refreshModels('openai')">
        <i class="fas fa-sync"></i> Refresh Models
    </button>
    <span id="openai-last-fetch" class="text-muted small"></span>
</div>
```

**JavaScript**:
```javascript
async function refreshModels(provider) {
    const button = event.target;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Fetching...';
    
    try {
        const response = await fetch(`/api/config/ai-models/fetch/${provider}?force_refresh=true`);
        const data = await response.json();
        
        if (response.ok) {
            updateModelDropdown(provider, data.models);
            updateLastFetchTime(provider, data.fetched_at);
            showNotification('success', `Fetched ${data.models.length} models from ${provider}`);
        } else {
            showNotification('error', `Failed to fetch models: ${data.error}`);
        }
    } catch (error) {
        showNotification('error', 'Network error while fetching models');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fas fa-sync"></i> Refresh Models';
    }
}

function updateModelDropdown(provider, models) {
    const select = document.getElementById(`${provider}-model-select`);
    select.innerHTML = models.map(m => 
        `<option value="${m.name}">${m.display_name}</option>`
    ).join('');
}
```

#### 4. Model Categorization Logic

Different model types for different functions:

```python
def categorize_openai_model(model_id: str, model_info: Dict) -> List[str]:
    """Determine model capabilities based on ID and metadata."""
    types = []
    
    # Embedding models
    if 'embedding' in model_id.lower():
        types.append('embeddings')
    
    # Chat/completion models
    if any(x in model_id.lower() for x in ['gpt-4', 'gpt-3.5', 'gpt-4o']):
        types.extend(['chatbot', 'catalog'])
    
    # Vision models (for OCR)
    if 'vision' in model_id.lower() or 'gpt-4o' in model_id.lower():
        types.append('ocr')
    
    return types
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (2 days)

**Tasks:**
1. Create `ai_actuarial/web/model_fetcher.py` with base classes
2. Implement `OpenAIModelFetcher` with API integration
3. Add in-memory caching layer
4. Create unit tests for model fetcher

**Deliverables:**
- ✅ Working OpenAI model fetching
- ✅ Unit tests covering happy path and error cases
- ✅ Cache mechanism with TTL

**Files to Create:**
- `ai_actuarial/web/model_fetcher.py`
- `tests/test_model_fetcher.py`

**Files to Modify:**
- `ai_actuarial/web/app.py` - Add new endpoint

### Phase 2: API Endpoint (1 day)

**Tasks:**
1. Add `/api/config/ai-models/fetch/{provider}` endpoint
2. Integrate with OpenAIModelFetcher
3. Add error handling and fallback to hardcoded list
4. Add API endpoint tests

**Deliverables:**
- ✅ Working REST endpoint
- ✅ Proper error handling
- ✅ Integration tests

**Files to Modify:**
- `ai_actuarial/web/app.py`

**Files to Create:**
- `tests/test_model_api.py`

### Phase 3: Frontend Integration (1 day)

**Tasks:**
1. Add "Refresh Models" button to Settings page
2. Implement JavaScript for dynamic model loading
3. Add loading states and error messages
4. Update model dropdowns dynamically

**Deliverables:**
- ✅ Working UI with refresh capability
- ✅ User-friendly error messages
- ✅ Visual feedback during loading

**Files to Modify:**
- `ai_actuarial/web/templates/settings.html`
- `ai_actuarial/web/static/js/settings.js` (if exists, or inline)

### Phase 4: Additional Providers (1 day)

**Tasks:**
1. Implement `MistralModelFetcher`
2. Implement `SiliconFlowModelFetcher`
3. Add provider-specific model categorization
4. Test with all providers

**Deliverables:**
- ✅ Support for Mistral and SiliconFlow
- ✅ Comprehensive test coverage

**Files to Modify:**
- `ai_actuarial/web/model_fetcher.py`
- `tests/test_model_fetcher.py`

### Phase 5: Polish & Documentation (0.5 day)

**Tasks:**
1. Add user documentation
2. Add inline code documentation
3. Update configuration guide
4. Add troubleshooting section

**Deliverables:**
- ✅ User-facing documentation
- ✅ Developer documentation
- ✅ Updated README if needed

---

## API Provider Endpoints

### OpenAI
- **Endpoint**: `GET https://api.openai.com/v1/models`
- **Auth**: `Authorization: Bearer {api_key}`
- **Response**:
```json
{
  "data": [
    {
      "id": "gpt-4-turbo",
      "object": "model",
      "created": 1712361441,
      "owned_by": "system"
    },
    ...
  ]
}
```
- **Documentation**: https://platform.openai.com/docs/api-reference/models/list

### Mistral
- **Endpoint**: `GET https://api.mistral.ai/v1/models`
- **Auth**: `Authorization: Bearer {api_key}`
- **Response**: Similar to OpenAI format
- **Documentation**: https://docs.mistral.ai/api/

### SiliconFlow
- **Endpoint**: TBD - Need to research their API
- **Auth**: TBD
- **Note**: May require custom integration

---

## Error Handling

### Scenarios & Responses

1. **No API Key Configured**
   - Return 401 with message: "API key not configured for {provider}"
   - Frontend: Show message to configure API key in .env

2. **API Call Failed**
   - Log error details
   - Return cached data if available (with `"cached": true, "stale": true`)
   - Otherwise return hardcoded fallback list
   - Frontend: Show warning banner

3. **Rate Limited**
   - Return cached data
   - Log warning
   - Frontend: Show "Using cached data, try again later"

4. **Invalid Response Format**
   - Log error with response details
   - Return hardcoded fallback
   - Alert developers to update parser

5. **Network Timeout**
   - Set timeout to 10 seconds
   - Return cached/fallback data
   - Frontend: Show retry button

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_model_fetcher.py`

```python
def test_openai_fetcher_success():
    """Test successful model fetching from OpenAI."""
    
def test_openai_fetcher_auth_error():
    """Test handling of invalid API key."""
    
def test_openai_fetcher_network_error():
    """Test handling of network failures."""
    
def test_model_categorization():
    """Test model type categorization logic."""
    
def test_cache_hit():
    """Test cache returns data without API call."""
    
def test_cache_expiry():
    """Test cache expires after TTL."""
```

### Integration Tests

**File**: `tests/test_model_api.py`

```python
def test_fetch_models_endpoint():
    """Test /api/config/ai-models/fetch/openai endpoint."""
    
def test_fetch_models_requires_auth():
    """Test endpoint requires proper permissions."""
    
def test_force_refresh_bypasses_cache():
    """Test force_refresh parameter."""
```

### Manual Testing Checklist

- [ ] Refresh models for OpenAI with valid API key
- [ ] Refresh models without API key configured
- [ ] Verify cache works (second call is instant)
- [ ] Test force refresh bypasses cache
- [ ] Verify fallback to hardcoded list on error
- [ ] Test with expired cache
- [ ] Test network timeout scenario
- [ ] Verify UI updates correctly
- [ ] Test with multiple providers
- [ ] Verify model selection persists after refresh

---

## Configuration

### New Environment Variables (Optional)

```bash
# Model fetching configuration
MODEL_CACHE_TTL_SECONDS=3600  # 1 hour default
MODEL_FETCH_TIMEOUT_SECONDS=10  # API call timeout
ENABLE_DYNAMIC_MODEL_FETCHING=true  # Feature flag
```

### Feature Flag

Add to `sites.yaml`:
```yaml
features:
  enable_dynamic_model_fetching: true
```

---

## Security Considerations

1. **API Key Protection**
   - Never expose API keys in responses
   - Only use keys from server-side .env
   - Validate permissions before allowing fetch

2. **Rate Limiting**
   - Implement per-user rate limiting (e.g., 10 fetches/hour)
   - Use cache to reduce provider API calls
   - Log excessive fetch attempts

3. **Input Validation**
   - Validate provider parameter (whitelist)
   - Sanitize all user inputs
   - Validate API responses before processing

4. **Error Information**
   - Don't leak sensitive error details to frontend
   - Log detailed errors server-side only
   - Return generic error messages to users

---

## Rollout Plan

### Stage 1: Development (Week 1)
- Implement core functionality
- Unit and integration tests
- Internal testing

### Stage 2: Beta (Week 2)
- Deploy to staging environment
- Test with real API keys
- Gather feedback from team

### Stage 3: Production (Week 3)
- Deploy behind feature flag
- Monitor error rates and performance
- Gradually enable for all users

### Rollback Plan
- Feature flag allows instant disable
- Fallback to hardcoded lists automatic
- No data migration needed

---

## Success Metrics

1. **Functionality**
   - ✅ Successfully fetches models from OpenAI
   - ✅ Cache hit rate > 80%
   - ✅ Fallback works in all error scenarios

2. **Performance**
   - API response time < 2 seconds (first fetch)
   - Cached response time < 100ms
   - No impact on page load time

3. **User Experience**
   - Users can discover new models immediately
   - Clear error messages guide users
   - Smooth loading experience (no blocking)

4. **Reliability**
   - 99.9% uptime for model selection
   - Graceful degradation on provider API failures
   - No user-facing errors from caching issues

---

## Future Enhancements

1. **Auto-refresh on Page Load** (Optional)
   - Refresh models in background on settings page load
   - Only if cache is expired
   - Show last fetch timestamp

2. **Model Metadata Display**
   - Show context window size
   - Display model capabilities
   - Show pricing information

3. **Custom Model Support**
   - Allow users to add custom fine-tuned models
   - Store custom models in database
   - Merge with fetched models

4. **Model Recommendations**
   - Suggest best model for each function
   - Based on cost, performance, capabilities
   - Show "Recommended" badge

5. **Provider Health Status**
   - Show provider API status
   - Warn if provider experiencing issues
   - Link to provider status page

---

## Dependencies

### Python Packages (Already Installed)
- `requests` - HTTP client for API calls
- `openai` - OpenAI SDK (optional, can use direct HTTP)
- `pyyaml` - YAML configuration
- `flask` - Web framework

### New Dependencies (None Required)
- All functionality possible with existing packages

---

## References

1. **OpenAI API Documentation**: https://platform.openai.com/docs/api-reference/models
2. **Mistral API Documentation**: https://docs.mistral.ai/api/
3. **RAGFlow Implementation**: Example of dynamic model fetching in production
4. **Flask Caching**: https://flask-caching.readthedocs.io/

---

## Questions & Decisions

### Open Questions
1. Should we use Redis for caching or in-memory cache?
   - **Decision**: Start with in-memory, upgrade to Redis if needed
2. How often should cache expire?
   - **Decision**: 1 hour (configurable)
3. Should model fetching be automatic or manual?
   - **Decision**: Manual with "Refresh" button (safer, more predictable)

### Design Decisions
- ✅ Keep hardcoded lists as fallback for reliability
- ✅ Cache results to minimize API calls
- ✅ Make feature opt-in via feature flag
- ✅ Implement OpenAI first, then expand

---

**Status**: Ready for Implementation  
**Next Step**: Review and approve this plan  
**Estimated Start Date**: After current PR is merged  
**Owner**: TBD
