from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_production_compose_uses_fastapi_env_and_keeps_features_in_yaml():
    src = (ROOT / "docker-compose.override.yml").read_text(encoding="utf-8")
    lines = {line.strip() for line in src.splitlines()}

    assert "FASTAPI_ENV=production" in src
    assert "- ENV=production" not in lines
    assert "- REQUIRE_AUTH=true" not in lines
    assert "- RATE_LIMIT_ENABLED=true" not in lines
    assert "FASTAPI_CORS_ORIGINS=${FASTAPI_CORS_ORIGINS:?FASTAPI_CORS_ORIGINS is required in production}" in src
    assert "VITE_API_BASE_URL=${VITE_API_BASE_URL:?VITE_API_BASE_URL is required in production}" in src
    assert "ENABLE_CSRF=${ENABLE_CSRF:-true}" in src
    assert "FASTAPI_SESSION_COOKIE_SECURE=${FASTAPI_SESSION_COOKIE_SECURE:-true}" in src
    assert "TRUST_PROXY=${TRUST_PROXY:-false}" in src
    assert "CONTENT_SECURITY_POLICY=${CONTENT_SECURITY_POLICY:-default-src" not in src
    assert "- CONTENT_SECURITY_POLICY" in src
    assert "CADDY_DOMAIN" not in src


def test_env_example_documents_comma_separated_cors_origins():
    src = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "FASTAPI_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173" in src
    assert 'FASTAPI_CORS_ORIGINS=["' not in src


def test_caddy_fail2ban_access_log_and_healthcheck_are_deployable():
    src = (ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert "output file /data/access.log" in src
    assert "/data/logs/access.log" not in src
    assert "http://localhost:80 {\n\tbind 127.0.0.1 [::1]\n\trespond \"ok\" 200\n}" in src


def test_public_caddyfile_uses_environment_placeholders_not_real_topology():
    src = (ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert "{$CADDY_APP_SITE_HOSTS:http://localhost:8080}" in src
    assert "{$CADDY_CROSS_SITE_HOST:http://localhost:8081}" in src
    assert "{$CADDY_CROSS_UPSTREAM:host.docker.internal:8501}" in src
    assert "aiinforsearch.com" not in src
    assert "cross.aiactuary.cn" not in src
    assert "172.28.0.1" not in src


def test_compose_does_not_pin_public_bridge_topology():
    src = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "172.28." not in src
    assert "host.docker.internal:host-gateway" in src
    assert "CADDY_APP_SITE_HOSTS=${CADDY_APP_SITE_HOSTS:-http://localhost:8080}" in src
    assert "CADDY_CROSS_UPSTREAM=${CADDY_CROSS_UPSTREAM:-host.docker.internal:8501}" in src
    assert "CONTENT_SECURITY_POLICY=${CONTENT_SECURITY_POLICY:-default-src" not in src
    assert "- CONTENT_SECURITY_POLICY" in src


def test_container_entrypoint_keeps_container_bind_reachable():
    src = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert 'FASTAPI_HOST:-0.0.0.0' in src
    assert 'FASTAPI_HOST:-127.0.0.1' not in src


def test_committed_sites_yaml_uses_safe_public_security_defaults():
    data = yaml.safe_load((ROOT / "config" / "sites.yaml").read_text(encoding="utf-8"))
    features = data["features"]
    server = data["server"]

    assert features["enable_csrf"] is True
    assert features["content_security_policy"]
    assert "default-src 'self'" in features["content_security_policy"]
    assert server["host"] == "127.0.0.1"
