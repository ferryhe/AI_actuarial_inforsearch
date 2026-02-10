# Security Policy

## Supported Versions

This project is currently in version 0.1.x. Security updates are provided for the latest release.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please follow these steps:

1. **Do NOT** create a public GitHub issue
2. Email the security team with details:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fixes (if any)

3. Allow reasonable time for the team to respond and fix the issue
4. Disclosure will be coordinated with the reporter

---

## Security Features

### Current Security Measures

#### Authentication & Authorization
- **CONFIG_WRITE_AUTH_TOKEN**: Required for configuration changes (optional, but recommended)
- **FILE_DELETION_AUTH_TOKEN**: Required for file deletion operations (optional)
- **Token-based authentication**: X-Auth-Token header validation

#### Input Validation
- **SQL Injection Protection**: SQLAlchemy ORM with parameterized queries
- **Path Traversal Prevention**: Sanitized task IDs and path validation
- **CSV Formula Injection Prevention**: Escaping of formula characters in CSV exports

#### Client-Side Protection
- **XSS Prevention**: Output escaping via `escapeHtml()` function
- **Safe DOM Manipulation**: Using `textContent` instead of `innerHTML`
- **Markdown Sanitization**: DOMPurify integration for markdown rendering

#### Data Integrity
- **SHA256 Checksums**: File deduplication and integrity verification
- **Database Transactions**: Atomic operations with rollback support

---

## Known Security Limitations

### Areas Requiring Additional Security Measures

1. **No Default Authentication**: Most API endpoints are accessible without authentication
   - **Mitigation**: Deploy behind network firewall or VPN
   - **Recommendation**: Implement application-level authentication

2. **No CSRF Protection**: POST/DELETE endpoints lack CSRF token validation
   - **Recommendation**: Implement Flask-SeaSurf or Flask-WTF CSRF

3. **No Rate Limiting**: API endpoints can be called without rate limits
   - **Recommendation**: Implement Flask-Limiter

4. **No Security Headers**: Missing CSP, X-Frame-Options, HSTS headers
   - **Recommendation**: Add security headers middleware

5. **Optional Token Authentication**: Config endpoints allow bypass if token not set
   - **Recommendation**: Make authentication mandatory

---

## Deployment Security Checklist

Use this checklist when deploying to production:

### Pre-Deployment

- [ ] Review and update all dependencies to latest secure versions
- [ ] Run security audit: `pip install pip-audit && pip-audit`
- [ ] Set strong random tokens for all authentication
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] Copy `.env.example` to `.env` and fill in values
- [ ] Ensure `.env` is in `.gitignore` and never committed

### Infrastructure

- [ ] Enable HTTPS with valid SSL certificate (Let's Encrypt recommended)
- [ ] Configure reverse proxy (Caddy, Nginx, or Apache)
- [ ] Set up firewall rules (allow only necessary ports)
- [ ] Use PostgreSQL instead of SQLite for production
- [ ] Enable database connection encryption
- [ ] Configure database backups (daily minimum)

### Application Configuration

- [ ] Set `FLASK_ENV=production`
- [ ] Set `FLASK_DEBUG=false`
- [ ] Set strong `FLASK_SECRET_KEY`
- [ ] Set `CONFIG_WRITE_AUTH_TOKEN` (mandatory)
- [ ] Set `FILE_DELETION_AUTH_TOKEN` (if file deletion enabled)
- [ ] Configure `MAX_CONTENT_LENGTH` to prevent large uploads
- [ ] Review and restrict file upload types

### Network Security

- [ ] Deploy behind firewall or VPN
- [ ] Use IP whitelisting if possible
- [ ] Enable DDoS protection
- [ ] Configure rate limiting on reverse proxy
- [ ] Set up intrusion detection system (IDS)

### Monitoring & Logging

- [ ] Configure centralized logging
- [ ] Set up log rotation
- [ ] Enable audit logging for sensitive operations
- [ ] Configure alerting for:
  - Failed authentication attempts
  - Unusual API usage patterns
  - System errors
  - File system changes
- [ ] Regular log review process

### Data Protection

- [ ] Encrypt database backups
- [ ] Secure file storage permissions (chmod 600 for sensitive files)
- [ ] Implement data retention policies
- [ ] Plan for secure data disposal

### Regular Maintenance

- [ ] Weekly dependency updates check
- [ ] Monthly security audit
- [ ] Quarterly penetration testing
- [ ] Annual security review

---

## Security Best Practices for Developers

### Code Review Guidelines

1. **Input Validation**: Always validate and sanitize user inputs
2. **Output Encoding**: Escape outputs to prevent XSS
3. **Authentication**: Use decorators to protect sensitive endpoints
4. **Authorization**: Verify user permissions before operations
5. **Error Handling**: Never expose sensitive information in error messages
6. **Logging**: Log security events but never log sensitive data
7. **Dependencies**: Keep all dependencies up to date
8. **Secrets**: Never commit secrets to version control

### Secure Coding Patterns

```python
# ✅ Good: Parameterized query
result = db.execute(text("SELECT * FROM files WHERE url = :url"), {"url": user_input})

# ❌ Bad: String concatenation
result = db.execute(f"SELECT * FROM files WHERE url = '{user_input}'")

# ✅ Good: Input validation
limit = min(max(int(request.args.get('limit', 20)), 1), 1000)

# ❌ Bad: No validation
limit = int(request.args.get('limit', 20))

# ✅ Good: Generic error message
return jsonify({"error": "Operation failed"}), 500

# ❌ Bad: Exposing exception details
return jsonify({"error": str(e)}), 500
```

### Testing Security Features

Always include security tests:

```python
def test_authentication_required():
    """Test that protected endpoint requires authentication"""
    response = client.post('/api/config/categories', json={})
    assert response.status_code == 403

def test_input_validation():
    """Test that invalid input is rejected"""
    response = client.get('/api/files?limit=999999')
    data = response.get_json()
    # Should be capped at maximum allowed
    assert len(data.get('files', [])) <= 1000

def test_csrf_protection():
    """Test that POST requests require CSRF token"""
    response = client.post('/api/files/update', json={})
    assert response.status_code in [400, 403]
```

---

## Incident Response Plan

### In Case of Security Breach

1. **Immediate Actions**:
   - Isolate affected systems
   - Preserve evidence and logs
   - Notify security team

2. **Investigation**:
   - Determine scope of breach
   - Identify compromised data
   - Review access logs

3. **Remediation**:
   - Patch vulnerabilities
   - Rotate all credentials and tokens
   - Update security measures

4. **Communication**:
   - Notify affected users
   - Document incident
   - Update security policies

5. **Post-Incident**:
   - Conduct post-mortem
   - Update security measures
   - Improve monitoring

---

## Security Resources

### External Resources

- **OWASP Top 10**: https://owasp.org/www-project-top-ten/
- **Flask Security**: https://flask.palletsprojects.com/en/latest/security/
- **Python Security**: https://python.readthedocs.io/en/stable/library/security_warnings.html
- **SQLAlchemy Security**: https://docs.sqlalchemy.org/en/latest/core/security.html
- **CWE Database**: https://cwe.mitre.org/

### Tools

- **pip-audit**: Check for known vulnerabilities in dependencies
- **bandit**: Python security linter
- **safety**: Dependency vulnerability scanner
- **CodeQL**: Semantic code analysis

---

## Version History

### 2026-02-10
- Initial security policy created
- Documented current security measures
- Added deployment checklist
- Created incident response plan

---

**For questions about this security policy, please contact the maintainers.**
