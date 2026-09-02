import http.client
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

PRODUCTION_CADDY_ENV = (
    "CADDY_APP_SITE_HOSTS=www.aiinforsearch.com, aiinforsearch.com",
    "CADDY_CROSS_SITE_HOST=cross.aiactuary.cn",
    "CADDY_CROSS_UPSTREAM=host.docker.internal:8501",
)


def _caddy_docker_args():
    args = ["docker", "run", "--rm"]
    for value in PRODUCTION_CADDY_ENV:
        args.extend(("--env", value))
    args.extend(
        (
            "--volume",
            f"{ROOT / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
            "caddy:2-alpine",
        )
    )
    return args


def _http_request(port, host, target="/"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", target, headers={"Host": host})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode("utf-8")
    finally:
        connection.close()


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def test_production_caddy_http_listener_and_runtime_redirect_contract():
    adapted = subprocess.run(
        _caddy_docker_args()
        + ["caddy", "adapt", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
        check=True,
        capture_output=True,
        text=True,
    )
    config = json.loads(adapted.stdout)
    servers = list(config["apps"]["http"]["servers"].values())
    public_http_servers = [server for server in servers if ":80" in server.get("listen", [])]
    port_80_listeners = [
        listener
        for server in servers
        for listener in server.get("listen", [])
        if listener.endswith(":80")
    ]

    assert len(public_http_servers) == 1
    assert port_80_listeners == [":80"]

    https_servers = [server for server in servers if ":443" in server.get("listen", [])]
    assert len(https_servers) == 1
    assert https_servers[0].get("automatic_https", {}).get("disable_redirects") is True
    assert sorted(item["dial"] for item in _walk_dicts(https_servers[0]) if "dial" in item) == [
        "api:5000",
        "frontend:5173",
        "host.docker.internal:8501",
    ]

    subprocess.run(
        _caddy_docker_args()
        + ["caddy", "validate", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
        check=True,
        capture_output=True,
        text=True,
    )

    runtime_config = {"apps": {"http": {"servers": {"http": public_http_servers[0]}}}}
    with tempfile.TemporaryDirectory(prefix="issue-331-caddy-") as temp_dir:
        runtime_config_path = Path(temp_dir) / "caddy.json"
        runtime_config_path.write_text(json.dumps(runtime_config), encoding="utf-8")

        container_name = f"issue-331-caddy-{uuid.uuid4().hex}"
        run_args = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container_name,
            "--publish",
            "127.0.0.1::80",
            "--volume",
            f"{runtime_config_path}:/etc/caddy/caddy.json:ro",
            "caddy:2-alpine",
            "caddy",
            "run",
            "--config",
            "/etc/caddy/caddy.json",
        ]
        subprocess.run(run_args, check=True, capture_output=True, text=True)

        try:
            published = subprocess.run(
                ["docker", "port", container_name, "80/tcp"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            port = int(published.rsplit(":", 1)[1])

            deadline = time.monotonic() + 10
            while True:
                try:
                    status, _, body = _http_request(port, "localhost:80")
                    if status == 200:
                        assert body == "ok"
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    logs = subprocess.run(
                        ["docker", "logs", container_name],
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    raise AssertionError(f"Caddy did not become ready:\n{logs.stderr}")
                time.sleep(0.1)

            for host in ("aiinforsearch.com", "www.aiinforsearch.com"):
                status, headers, _ = _http_request(port, host, "/database?category=AI")
                assert status in (301, 308)
                assert headers["Location"] == ("https://www.aiinforsearch.com/database?category=AI")

            for host in ("unrelated.example", "cross.aiactuary.cn"):
                status, headers, body = _http_request(port, host, "/probe?source=host")
                assert status == 421
                assert "Location" not in headers
                assert host not in body
                assert host not in "\n".join(f"{key}: {value}" for key, value in headers.items())
        finally:
            subprocess.run(
                ["docker", "rm", "--force", container_name],
                check=False,
                capture_output=True,
                text=True,
            )


def test_production_compose_uses_fastapi_env_and_keeps_features_in_yaml():
    src = (ROOT / "docker-compose.override.yml").read_text(encoding="utf-8")
    lines = {line.strip() for line in src.splitlines()}

    assert "FASTAPI_ENV=production" in src
    assert "- ENV=production" not in lines
    assert "- REQUIRE_AUTH=true" not in lines
    assert "- RATE_LIMIT_ENABLED=true" not in lines
    assert (
        "FASTAPI_CORS_ORIGINS=${FASTAPI_CORS_ORIGINS:?FASTAPI_CORS_ORIGINS is required in production}"
        in src
    )
    assert (
        "VITE_API_BASE_URL=${VITE_API_BASE_URL:?VITE_API_BASE_URL is required in production}" in src
    )
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
    assert "http://:80 {" in src
    assert "@health host localhost" in src
    assert 'respond "ok" 200' in src


def test_public_caddyfile_keeps_runtime_topology_in_environment_placeholders():
    src = (ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert "{$CADDY_APP_SITE_HOSTS:http://localhost:8080}" in src
    assert "{$CADDY_CROSS_SITE_HOST:http://localhost:8081}" in src
    assert "{$CADDY_CROSS_UPSTREAM:host.docker.internal:8501}" in src
    assert "@app_hosts host aiinforsearch.com www.aiinforsearch.com" in src
    assert "redir https://www.aiinforsearch.com{uri} permanent" in src
    assert "cross.aiactuary.cn" not in src
    assert "172.28.0.1" not in src
    assert """{$CADDY_CROSS_SITE_HOST:http://localhost:8081} {
\timport json_access_log
\timport baseline_security_headers

\treverse_proxy {$CADDY_CROSS_UPSTREAM:host.docker.internal:8501}
}
""" in src


def test_compose_does_not_pin_public_bridge_topology():
    src = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(src)

    assert "172.28." not in src
    assert "host.docker.internal:host-gateway" in src
    assert "CADDY_APP_SITE_HOSTS=${CADDY_APP_SITE_HOSTS:-http://localhost:8080}" in src
    assert "CADDY_CROSS_UPSTREAM=${CADDY_CROSS_UPSTREAM:-host.docker.internal:8501}" in src
    assert "CONTENT_SECURITY_POLICY=${CONTENT_SECURITY_POLICY:-default-src" not in src
    assert "- CONTENT_SECURITY_POLICY" in src
    assert "ports" not in data["services"]["api"]
    assert "ports" not in data["services"]["frontend"]
    assert data["services"]["caddy"]["ports"] == [
        "${CADDY_HTTP_PORT:-80}:80",
        "${CADDY_HTTPS_PORT:-443}:443",
    ]


def test_container_entrypoint_keeps_container_bind_reachable():
    src = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert "FASTAPI_HOST:-0.0.0.0" in src
    assert "FASTAPI_HOST:-127.0.0.1" not in src


def test_committed_sites_yaml_uses_safe_public_security_defaults():
    data = yaml.safe_load((ROOT / "config" / "sites.yaml").read_text(encoding="utf-8"))
    features = data["features"]
    server = data["server"]

    assert features["enable_csrf"] is True
    assert features["content_security_policy"]
    assert "default-src 'self'" in features["content_security_policy"]
    assert server["host"] == "127.0.0.1"


def test_frontend_fonts_do_not_depend_on_google_hosts():
    client_root = ROOT / "client"
    frontend_suffixes = {".css", ".html", ".js", ".jsx", ".ts", ".tsx"}
    google_font_hosts = ("fonts.googleapis.com", "fonts.gstatic.com")
    violations = []

    for path in client_root.rglob("*"):
        if not path.is_file() or path.suffix not in frontend_suffixes:
            continue
        source = path.read_text(encoding="utf-8")
        for host in google_font_hosts:
            if host in source:
                violations.append(f"{path.relative_to(ROOT).as_posix()}: {host}")

    assert violations == []

    css = (client_root / "src" / "index.css").read_text(encoding="utf-8")
    assert "system-ui, sans-serif" in css
    assert "Georgia, serif" in css
