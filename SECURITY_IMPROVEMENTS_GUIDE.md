# 安全改进快速指南 / Quick Security Improvements Guide

本指南提供了基于代码审查的快速安全改进步骤。
This guide provides quick steps to improve security based on code review findings.

---

## 🚨 立即执行 / Immediate Actions (Day 1)

### 1. 更新依赖项 / Update Dependencies

```bash
# 更新Pillow以修复安全漏洞 / Update Pillow to fix vulnerabilities
pip install --upgrade "Pillow>=10.2.0"

# 检查其他漏洞 / Check for other vulnerabilities
pip install pip-audit
pip-audit
```

### 2. 设置环境变量 / Set Up Environment Variables

```bash
# 复制示例文件 / Copy example file
cp .env.example .env

# 生成强密钥 / Generate strong keys
python3 << 'EOF'
import secrets
print("CONFIG_WRITE_AUTH_TOKEN=" + secrets.token_urlsafe(32))
print("FILE_DELETION_AUTH_TOKEN=" + secrets.token_urlsafe(32))
print("FLASK_SECRET_KEY=" + secrets.token_urlsafe(32))
EOF

# 编辑.env文件并添加生成的密钥
# Edit .env and add the generated keys
```

### 3. 启用基本安全功能 / Enable Basic Security Features

编辑 `.env` 文件:
```bash
# 要求配置写入认证
CONFIG_WRITE_AUTH_TOKEN=<your-generated-token>

# 仅在需要时启用文件删除
ENABLE_FILE_DELETION=false
FILE_DELETION_AUTH_TOKEN=<your-generated-token>

# 设置Flask密钥
FLASK_SECRET_KEY=<your-generated-secret>
```

---

## 📋 第一周 / Week 1: Critical Security Fixes

### 步骤1: 添加输入验证 / Step 1: Add Input Validation

在 `ai_actuarial/web/app.py` 中添加输入验证辅助函数:

```python
# Add after imports (around line 30)
def validate_limit(limit: int, default: int = 20, max_limit: int = 1000) -> int:
    """Validate and sanitize limit parameter."""
    try:
        limit = int(limit)
        return min(max(limit, 1), max_limit)
    except (ValueError, TypeError):
        return default

def validate_offset(offset: int, default: int = 0) -> int:
    """Validate and sanitize offset parameter."""
    try:
        offset = int(offset)
        return max(offset, 0)
    except (ValueError, TypeError):
        return default
```

然后在端点中使用:
```python
# In api_files() function (around line 326)
limit = validate_limit(request.args.get('limit', 20))
offset = validate_offset(request.args.get('offset', 0))
```

### 步骤2: 添加CSRF保护 / Step 2: Add CSRF Protection

```bash
# 安装Flask-SeaSurf
pip install Flask-SeaSurf
```

在 `ai_actuarial/web/app.py` 中:
```python
# Add after Flask import (around line 1)
from flask_seasurf import SeaSurf

# Add after app creation (around line 214)
csrf = SeaSurf(app)

# For API endpoints that should be exempt (if needed)
@csrf.exempt
@app.route('/api/some-public-endpoint', methods=['POST'])
def public_endpoint():
    pass
```

### 步骤3: 添加安全响应头 / Step 3: Add Security Headers

在 `ai_actuarial/web/app.py` 中添加 (around line 214, after app creation):

```python
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Enable XSS filter (legacy but doesn't hurt)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self' data:;"
    )
    
    # Only enable HSTS if using HTTPS in production
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    return response
```

### 步骤4: 改进错误处理 / Step 4: Improve Error Handling

在 `ai_actuarial/web/app.py` 中添加通用错误处理器:

```python
@app.errorhandler(500)
def handle_internal_error(error):
    """Handle internal server errors without exposing details."""
    logger.exception("Internal server error occurred")
    return jsonify({
        "error": "An internal error occurred. Please contact support."
    }), 500

@app.errorhandler(404)
def handle_not_found(error):
    """Handle 404 errors."""
    logger.warning(f"404 error: {request.path}")
    return jsonify({
        "error": "Resource not found"
    }), 404

@app.errorhandler(403)
def handle_forbidden(error):
    """Handle 403 forbidden errors."""
    logger.warning(f"403 forbidden: {request.path}")
    return jsonify({
        "error": "Access forbidden"
    }), 403
```

然后替换所有 `return jsonify({"error": str(e)}), 500` 为:
```python
logger.exception("Operation failed")
return jsonify({"error": "Operation failed"}), 500
```

---

## 🔧 第二周 / Week 2: Add Rate Limiting

### 安装Flask-Limiter / Install Flask-Limiter

```bash
pip install Flask-Limiter
```

### 配置限流 / Configure Rate Limiting

在 `ai_actuarial/web/app.py`:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# After app creation
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://"
)

# Apply stricter limits to specific endpoints
@app.route('/api/collections/run', methods=['POST'])
@limiter.limit("5 per minute")
def api_collections_run():
    # existing code
    pass

@app.route('/api/export', methods=['GET'])
@limiter.limit("10 per hour")
def api_export():
    # existing code
    pass
```

---

## 🛡️ 第三周 / Week 3: Add Authentication

### 选项A: 简单API密钥认证 / Option A: Simple API Key Auth

在 `ai_actuarial/web/app.py`:

```python
from functools import wraps

def require_api_key(f):
    """Decorator to require API key authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        expected_key = os.getenv('API_KEY')
        
        if not expected_key:
            logger.error("API_KEY not configured")
            return jsonify({"error": "Authentication not configured"}), 500
        
        if not api_key or api_key != expected_key:
            logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
            return jsonify({"error": "Unauthorized"}), 401
        
        return f(*args, **kwargs)
    return decorated_function

# Apply to protected endpoints
@app.route('/api/files')
@require_api_key
def api_files():
    # existing code
    pass
```

在 `.env` 中添加:
```bash
# 生成API密钥
python -c "import secrets; print('API_KEY=' + secrets.token_urlsafe(32))"
```

### 选项B: Flask-Login (更完整) / Option B: Flask-Login (More Complete)

```bash
pip install Flask-Login
```

参考Flask-Login文档实现完整的会话管理。

---

## 📊 验证改进 / Verify Improvements

### 1. 运行安全扫描 / Run Security Scans

```bash
# 安装安全工具
pip install bandit safety

# 运行Bandit安全检查
bandit -r ai_actuarial/ -f json -o bandit-report.json

# 检查依赖漏洞
safety check --json

# 或使用pip-audit
pip-audit --format=json
```

### 2. 测试认证 / Test Authentication

```bash
# 测试未授权访问被拒绝
curl -X POST http://localhost:5000/api/config/categories \
  -H "Content-Type: application/json" \
  -d '{"categories": []}'
# 应返回403 Forbidden

# 测试授权访问成功
curl -X POST http://localhost:5000/api/config/categories \
  -H "Content-Type: application/json" \
  -H "X-Auth-Token: your-token-here" \
  -d '{"categories": []}'
# 应成功
```

### 3. 测试CSRF保护 / Test CSRF Protection

```bash
# 测试无CSRF令牌的POST请求被拒绝
curl -X POST http://localhost:5000/api/files/update \
  -H "Content-Type: application/json" \
  -d '{"url": "test", "category": "test"}'
# 应返回400或403
```

### 4. 测试速率限制 / Test Rate Limiting

```bash
# 快速发送多个请求
for i in {1..10}; do
  curl http://localhost:5000/api/files?limit=10
done
# 应触发速率限制
```

---

## 📝 检查清单 / Checklist

部署前确认以下项目 / Confirm before deployment:

- [ ] ✅ 已更新Pillow到>=10.2.0
- [ ] ✅ 已设置所有必需的环境变量
- [ ] ✅ .env文件已添加到.gitignore
- [ ] ✅ 已添加输入验证
- [ ] ✅ 已添加CSRF保护
- [ ] ✅ 已添加安全响应头
- [ ] ✅ 已改进错误处理
- [ ] ✅ 已添加速率限制
- [ ] ✅ 已实施认证机制
- [ ] ✅ 已运行安全扫描
- [ ] ✅ 已测试所有安全功能
- [ ] ✅ 已配置HTTPS (生产环境)
- [ ] ✅ 已设置防火墙规则
- [ ] ✅ 已配置日志监控

---

## 🆘 故障排除 / Troubleshooting

### CSRF令牌问题 / CSRF Token Issues

如果CSRF保护导致问题:
```python
# 对特定端点禁用CSRF (仅用于调试)
@csrf.exempt
@app.route('/api/endpoint')
def endpoint():
    pass
```

### 速率限制问题 / Rate Limiting Issues

如果速率限制过于严格:
```python
# 增加限制
@limiter.limit("100 per minute")  # 增加到100
def endpoint():
    pass

# 或为特定IP豁免
limiter.exempt("127.0.0.1")
```

### 认证问题 / Authentication Issues

检查环境变量:
```bash
# 验证令牌已设置
python << 'EOF'
import os
from dotenv import load_dotenv
load_dotenv()
print("CONFIG_WRITE_AUTH_TOKEN:", "SET" if os.getenv("CONFIG_WRITE_AUTH_TOKEN") else "NOT SET")
print("API_KEY:", "SET" if os.getenv("API_KEY") else "NOT SET")
EOF
```

---

## 📚 更多资源 / Additional Resources

- [完整代码审查报告](CODE_REVIEW_REPORT.md)
- [安全策略](SECURITY.md)
- [Flask安全文档](https://flask.palletsprojects.com/en/latest/security/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

---

**注意**: 这些改进是基于代码审查的建议。请在开发环境中彻底测试后再部署到生产环境。

**Note**: These improvements are based on code review recommendations. Please test thoroughly in a development environment before deploying to production.
