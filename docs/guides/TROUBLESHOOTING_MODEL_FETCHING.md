# Dynamic Model Fetching - Troubleshooting Guide
# 动态模型获取 - 故障排除指南

## Common Issues and Solutions / 常见问题及解决方案

### Issue 1: Models not appearing / 问题1：模型未显示

**Symptoms / 症状**:
- Empty model dropdown in Settings page
- 设置页面中模型下拉菜单为空
- Only "Local" models showing
- 只显示"本地"模型

**Causes / 原因**:
1. API keys not configured / API密钥未配置
2. Network connectivity issues / 网络连接问题
3. API rate limits / API速率限制

**Solutions / 解决方案**:

```bash
# 1. Check if API keys are set
echo $OPENAI_API_KEY
echo $MISTRAL_API_KEY
echo $SILICONFLOW_API_KEY
echo $OPENROUTER_API_KEY
echo $DASHSCOPE_API_KEY
echo $MINIMAX_API_KEY

# 2. Verify API key permissions
# OpenAI: https://platform.openai.com/api-keys
# Mistral: https://console.mistral.ai/
# SiliconFlow: Check your provider dashboard

# 3. Check logs for errors
tail -f data/app.log | grep -i "model"

# 4. Test API connectivity
python -c "
from openai import OpenAI
client = OpenAI()
print(client.models.list())
"
```

**Expected Log Messages / 预期日志消息**:
```
INFO: Initializing model cache on startup...
INFO: Refreshing model cache from providers...
INFO: Fetched 17 OpenAI models from API
INFO: Fetched 14 Mistral models from API
INFO: Model cache initialization complete
```

### Issue 2: Stale models in cache / 问题2：缓存中的模型过时

**Symptoms / 症状**:
- New models not appearing
- 新模型未出现
- Old/deprecated models still showing
- 仍显示旧的/已弃用的模型

**Solution / 解决方案**:

Force refresh the cache:

强制刷新缓存：

```python
# Method 1: Programmatically
from ai_actuarial.llm_models import refresh_models
refresh_models()

# Method 2: HTTP read endpoint
# Requires the same config.read access as the model catalog endpoint
curl "http://127.0.0.1:8000/api/config/model-catalog?refresh=true"
curl "http://127.0.0.1:8000/api/config/ai-models?refresh=true"

# Method 3: Restart the application
# The cache will refresh on startup
```

Or wait for automatic refresh (24 hours).

或等待自动刷新（24小时）。

More details: [AI Model Catalog](AI_MODEL_CATALOG.md).

### Issue 3: Slow model loading / 问题3：模型加载缓慢

**Symptoms / 症状**:
- Settings page takes >5 seconds to load
- 设置页面加载超过5秒
- First request is slow
- 首次请求很慢

**Explanation / 解释**:

This is expected behavior on first load:
- Cache is empty / 缓存为空
- Fetches from multiple APIs / 从多个API获取
- Subsequent requests are fast (<1ms) / 后续请求很快（<1毫秒）

**Solution / 解决方案**:

Pre-warm cache at startup (already implemented):

启动时预热缓存（已实现）：

```python
# This runs automatically in background thread
initialize_models()
```

### Issue 4: API errors / 问题4：API错误

**Symptoms / 症状**:
- Warning logs about failed API calls
- 关于API调用失败的警告日志
- "Failed to fetch X models" messages
- "获取X模型失败"消息

**Common Causes / 常见原因**:

1. **Invalid API Key**
   ```
   WARNING: Failed to fetch OpenAI models: AuthenticationError
   ```
   Solution: Check and update your API key / 检查并更新API密钥

2. **Rate Limit**
   ```
   WARNING: Failed to fetch OpenAI models: RateLimitError
   ```
   Solution: Wait and retry, or upgrade API plan / 等待重试或升级API计划

3. **Network Timeout**
   ```
   WARNING: Failed to fetch OpenAI models: Timeout
   ```
   Solution: Check network connectivity / 检查网络连接

**Automatic Fallback / 自动回退**:

Good news: The system automatically falls back to curated default models, so the app continues to work.

好消息：系统自动回退到维护过的默认模型，所以应用继续工作！

### Issue 5: Thread safety issues / 问题5：线程安全问题

**Symptoms / 症状**:
- Inconsistent model lists
- 模型列表不一致
- Race condition errors
- 竞态条件错误

**Solution / 解决方案**:

The code is thread-safe by design. If you see issues:

代码设计上是线程安全的。如果看到问题：

1. Check if you're using the singleton cache / 检查是否使用单例缓存
   ```python
   # CORRECT
   cache = get_model_cache()
   
   # WRONG - creates multiple instances
   cache = ModelCache()
   ```

2. Verify lock usage / 验证锁的使用
   ```python
   # Internal implementation uses locks
   with self._lock:
       self._refresh_models()
   ```

## Debug Mode / 调试模式

Enable debug logging:

启用调试日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Or in .env
DEBUG=true
LOG_LEVEL=DEBUG
```

Check cache state:

检查缓存状态：

```python
from ai_actuarial.llm_models import get_model_cache

cache = get_model_cache()
print(f"Initialized: {cache._initialized}")
print(f"Last refresh: {cache._last_refresh}")
print(f"Cached providers: {list(cache._models.keys())}")
```

## Performance Optimization / 性能优化

### Current Performance / 当前性能
- First load: ~2-5 seconds (API calls)
- Cached load: <1ms
- Memory: ~50KB for cache

### Optimization Tips / 优化建议

1. **Reduce Refresh Interval** (if needed)
   ```python
   # In llm_models.py
   _model_cache = ModelCache(refresh_interval_hours=12)  # Default: 24
   ```

2. **Skip Unused Providers**
   ```python
   # Modify _refresh_models() to skip providers
   if not os.getenv('MISTRAL_API_KEY'):
       new_models["mistral"] = DEFAULT_MODELS["mistral"]
   ```

3. **Async Fetching** (future enhancement)
   - Fetch from providers in parallel
   - Use asyncio for faster initialization

## Monitoring / 监控

### Key Metrics / 关键指标

Monitor these in production:

在生产环境中监控这些：

1. **Cache Hit Rate**
   - Should be >99% after warmup
   - 预热后应>99%

2. **API Call Frequency**
   - Should be ~1 per 24 hours per provider
   - 每个提供商约24小时一次

3. **Fallback Rate**
   - Track how often defaults are used
   - 跟踪使用默认值的频率

4. **Response Time**
   - Cached: <1ms
   - Uncached: <5s

### Health Check / 健康检查

```python
def health_check():
    """Check if model cache is healthy."""
    cache = get_model_cache()
    
    # Check if initialized
    if not cache._initialized:
        return "WARN: Cache not initialized"
    
    # Check refresh time
    import datetime
    age = datetime.datetime.now() - cache._last_refresh
    if age > datetime.timedelta(hours=48):
        return "WARN: Cache very stale"
    
    # Check model counts
    for provider in ['openai', 'mistral', 'local']:
        if provider not in cache._models:
            return f"ERROR: Missing provider {provider}"
        if len(cache._models[provider]) == 0:
            return f"WARN: No models for {provider}"
    
    return "OK"
```

## Contact Support / 联系支持

If issues persist after trying these solutions:

如果尝试这些解决方案后问题仍然存在：

1. Check GitHub Issues / 查看GitHub问题
2. Create detailed bug report with:
   - Error logs / 错误日志
   - Environment info / 环境信息
   - Steps to reproduce / 复现步骤
3. Include cache state dump / 包括缓存状态转储

---

**Last Updated**: 2026-02-17  
**Version**: 1.0
