import gzip
import http.client
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]

TEST_CADDY_DEPLOYMENTS = (
    {
        "CADDY_APP_SITE_HOSTS": "app-one.example.test, www.app-one.example.test",
        "CADDY_APP_REDIRECT_HOSTS": "app-one.example.test www.app-one.example.test",
        "CADDY_APP_REDIRECT_ORIGIN": "https://www.app-one.example.test",
    },
    {
        "CADDY_APP_SITE_HOSTS": "app-two.example.test, www.app-two.example.test",
        "CADDY_APP_REDIRECT_HOSTS": "app-two.example.test www.app-two.example.test",
        "CADDY_APP_REDIRECT_ORIGIN": "https://www.app-two.example.test",
    },
)


class _CaddyStaticUpstream(SimpleHTTPRequestHandler):
    def end_headers(self):
        if hasattr(self, "_current_etag"):
            self.send_header("ETag", self._current_etag)
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-eval'")
        self.send_header("X-Content-Type-Options", "upstream")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "unsafe-url")
        self.send_header("Permissions-Policy", "camera=*")
        self.send_header("Cache-Control", "public, max-age=60")
        super().end_headers()

    def send_head(self):
        request_path = self.path.split("?", 1)[0]
        if not Path(self.translate_path(self.path)).is_file() and request_path != "/":
            self.path = "/index.html"
        file_path = Path(self.translate_path(self.path))
        if file_path.is_file():
            stat = file_path.stat()
            self._current_etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
            if self.headers.get("If-None-Match") in (self._current_etag, "*"):
                self.send_response(304)
                self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
                self.end_headers()
                return None
        return super().send_head()

    def do_GET(self):
        request_path = self.path.split("?", 1)[0]
        if request_path == "/assets/redirect-A1b2C3d4.js":
            self.send_response(302)
            self.send_header("Location", "/assets/index-D6dVqAIK.js")
            self.end_headers()
            return
        if request_path.startswith("/api/"):
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def _caddy_docker_args(environment, caddyfile_path=None):
    args = ["docker", "run", "--rm"]
    for name, value in environment.items():
        args.extend(("--env", f"{name}={value}"))
    args.extend(
        (
            "--volume",
            f"{caddyfile_path or ROOT / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
            "--volume",
            f"{ROOT / 'Caddyfile.app'}:/etc/caddy/app.caddy:ro",
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


def _http_request_bytes(port, host, target="/", request_headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        headers = {"Host": host}
        headers.update(request_headers or {})
        connection.request("GET", target, headers=headers)
        response = connection.getresponse()
        return response.status, response.getheaders(), response.read()
    finally:
        connection.close()


def _http_request_headers(port, host, target="/"):
    status, headers, body = _http_request_bytes(port, host, target)
    return status, headers, body.decode("utf-8")


def _unused_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


@pytest.mark.parametrize("caddy_environment", TEST_CADDY_DEPLOYMENTS, ids=("app-one", "app-two"))
def test_caddy_http_listener_and_runtime_redirect_contract(caddy_environment):
    adapted = subprocess.run(
        _caddy_docker_args(caddy_environment)
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
        "frontend:5173",
    ]

    subprocess.run(
        _caddy_docker_args(caddy_environment)
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

            redirect_origin = caddy_environment["CADDY_APP_REDIRECT_ORIGIN"]
            for host in caddy_environment["CADDY_APP_REDIRECT_HOSTS"].split():
                status, headers, _ = _http_request(port, host, "/database?category=AI")
                assert status == 308
                assert headers["Location"] == f"{redirect_origin}/database?category=AI"

            for host in ("unrelated.example.test",):
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


def test_caddy_app_fragment_composes_with_a_host_managed_site():
    caddy_environment = TEST_CADDY_DEPLOYMENTS[0]
    with tempfile.TemporaryDirectory(prefix="issue-328-caddy-compose-") as temp_dir:
        composed_caddyfile = Path(temp_dir) / "Caddyfile"
        composed_caddyfile.write_text(
            "{\n\tauto_https disable_redirects\n}\n"
            "import /etc/caddy/app.caddy\n\n"
            'http://independent.example.test {\n\trespond "host-managed site" 200\n}\n',
            encoding="utf-8",
        )
        adapted = subprocess.run(
            _caddy_docker_args(caddy_environment, composed_caddyfile)
            + ["caddy", "adapt", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
            check=True,
            capture_output=True,
            text=True,
        )
        config = json.loads(adapted.stdout)
        servers = list(config["apps"]["http"]["servers"].values())
        public_http_servers = [server for server in servers if ":80" in server.get("listen", [])]
        assert len(public_http_servers) == 1

        runtime_config_path = Path(temp_dir) / "caddy.json"
        runtime_config_path.write_text(
            json.dumps({"apps": {"http": {"servers": {"http": public_http_servers[0]}}}}),
            encoding="utf-8",
        )
        container_name = f"issue-328-caddy-compose-{uuid.uuid4().hex}"
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

            status, _, body = _http_request(port, "independent.example.test")
            assert status == 200
            assert body == "host-managed site"
            status, _, _ = _http_request(port, "unconfigured.example.test")
            assert status == 421
        finally:
            subprocess.run(
                ["docker", "rm", "--force", container_name],
                check=False,
                capture_output=True,
                text=True,
            )


@pytest.mark.parametrize(
    "content_security_policy",
    [None, "", "default-src 'self'; img-src 'self' data: blob: https:"],
)
def test_caddy_replaces_upstream_security_headers_for_app_and_api_routes(
    content_security_policy,
):
    upstream_root = tempfile.TemporaryDirectory(prefix="issue-328-static-")
    static_root = Path(upstream_root.name)
    assets_root = static_root / "assets"
    assets_root.mkdir()
    html_body = b"<!doctype html><html><body><div id=app>SPA home</div></body></html>"
    js_body = b"console.log('hashed javascript asset');\n" * 80
    css_body = b".app { color: #123456; }\n" * 100
    (static_root / "index.html").write_bytes(html_body)
    (assets_root / "index-D6dVqAIK.js").write_bytes(js_body)
    (assets_root / "index-Abc123_9.css").write_bytes(css_body)
    (assets_root / "logo.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg'></svg>", encoding="utf-8"
    )
    upstream = ThreadingHTTPServer(
        ("0.0.0.0", 0), partial(_CaddyStaticUpstream, directory=str(static_root))
    )
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    caddy_port = _unused_port()
    container_name = f"issue-353-caddy-{uuid.uuid4().hex}"

    with tempfile.TemporaryDirectory(prefix="issue-353-caddy-") as temp_dir:
        runtime_caddyfile = Path(temp_dir) / "Caddyfile"
        runtime_caddy_app = Path(temp_dir) / "Caddyfile.app"
        runtime_caddyfile.write_text((ROOT / "Caddyfile").read_text(encoding="utf-8"))
        runtime_caddy_app.write_text(
            (ROOT / "Caddyfile.app")
            .read_text(encoding="utf-8")
            .replace("api:5000", f"host.docker.internal:{upstream.server_port}")
            .replace("frontend:5173", f"host.docker.internal:{upstream.server_port}"),
            encoding="utf-8",
        )
        run_args = [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container_name,
            "--publish",
            f"127.0.0.1::{caddy_port}",
            "--env",
            f"CADDY_APP_SITE_HOSTS=http://localhost:{caddy_port}",
        ]
        if sys.platform.startswith("linux"):
            run_args.extend(("--add-host", "host.docker.internal:host-gateway"))
        if content_security_policy is not None:
            run_args.extend(("--env", f"CONTENT_SECURITY_POLICY={content_security_policy}"))
        subprocess.run(
            run_args
            + [
                "--volume",
                f"{runtime_caddyfile}:/etc/caddy/Caddyfile:ro",
                "--volume",
                f"{runtime_caddy_app}:/etc/caddy/app.caddy:ro",
                "caddy:2-alpine",
                "caddy",
                "run",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        try:
            published = subprocess.run(
                ["docker", "port", container_name, f"{caddy_port}/tcp"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            port = int(published.rsplit(":", 1)[1])
            deadline = time.monotonic() + 10
            while True:
                try:
                    status, _, _ = _http_request_headers(port, f"localhost:{caddy_port}")
                    if status == 200:
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

            expected_csp = content_security_policy or (
                "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
                "form-action 'self'; img-src 'self' data: blob: https:; font-src 'self' data:; "
                "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' ws: wss:"
            )
            expected = {
                "content-security-policy": expected_csp,
                "x-content-type-options": "nosniff",
                "x-frame-options": "DENY",
                "referrer-policy": "strict-origin-when-cross-origin",
                "permissions-policy": "geolocation=(), microphone=(), camera=()",
                "strict-transport-security": "max-age=31536000",
            }

            for target, content_types, body in (
                (
                    "/assets/index-D6dVqAIK.js",
                    ("application/javascript", "text/javascript"),
                    js_body,
                ),
                (
                    "/assets/index-Abc123_9.css",
                    ("text/css",),
                    css_body,
                ),
            ):
                upstream_status, upstream_headers, upstream_body = _http_request_bytes(
                    upstream.server_port, "localhost", target
                )
                assert upstream_status == 200
                assert [value for key, value in upstream_headers if key.lower() == "content-type"][
                    0
                ] in content_types
                assert upstream_body == body

            upstream_status, upstream_headers, upstream_body = _http_request_bytes(
                upstream.server_port, "localhost", "/assets/missing-D6dVqAIK.js"
            )
            assert upstream_status == 200
            assert [value for key, value in upstream_headers if key.lower() == "content-type"] == [
                "text/html"
            ]
            assert upstream_body == html_body
            fallback_last_modified = next(
                value for key, value in upstream_headers if key.lower() == "last-modified"
            )
            fallback_etag = next(value for key, value in upstream_headers if key.lower() == "etag")
            upstream_status, _, _ = _http_request_bytes(
                upstream.server_port,
                "localhost",
                "/assets/missing-D6dVqAIK.js",
                {"If-Modified-Since": fallback_last_modified, "Cache-Control": "no-cache"},
            )
            assert upstream_status == 304
            upstream_status, upstream_headers, _ = _http_request_bytes(
                upstream.server_port,
                "localhost",
                "/assets/missing-D6dVqAIK.js",
                {"If-None-Match": fallback_etag, "Cache-Control": "no-cache"},
            )
            assert upstream_status == 304
            assert not any(key.lower() == "content-type" for key, _ in upstream_headers)

            _, existing_headers, _ = _http_request_bytes(
                upstream.server_port, "localhost", "/assets/index-D6dVqAIK.js"
            )
            existing_last_modified = next(
                value for key, value in existing_headers if key.lower() == "last-modified"
            )
            existing_etag = next(value for key, value in existing_headers if key.lower() == "etag")
            upstream_status, _, _ = _http_request_bytes(
                upstream.server_port,
                "localhost",
                "/assets/index-D6dVqAIK.js",
                {"If-Modified-Since": existing_last_modified, "Cache-Control": "no-cache"},
            )
            assert upstream_status == 304
            upstream_status, upstream_headers, _ = _http_request_bytes(
                upstream.server_port,
                "localhost",
                "/assets/index-D6dVqAIK.js",
                {"If-None-Match": existing_etag, "Cache-Control": "no-cache"},
            )
            assert upstream_status == 304
            assert not any(key.lower() == "content-type" for key, _ in upstream_headers)
            for target in (
                "/",
                "/index.html",
                "/login",
                "/missing-spa-route",
                "/chat",
                "/files/1/preview",
                "/api/health",
            ):
                status, headers, _ = _http_request_headers(port, f"localhost:{caddy_port}", target)
                assert status == 200
                for name, value in expected.items():
                    values = [item for key, item in headers if key.lower() == name]
                    assert values == [value]
                assert "unsafe-eval" not in expected["content-security-policy"]

            status, headers, body = _http_request_bytes(port, f"localhost:{caddy_port}", "/chat")
            assert status == 200
            assert body == html_body
            assert [value for key, value in headers if key.lower() == "content-type"] == [
                "text/html"
            ]

            for target in ("/", "/index.html", "/index", "/chat"):
                status, headers, _ = _http_request_bytes(port, f"localhost:{caddy_port}", target)
                assert status == 200
                assert [value for key, value in headers if key.lower() == "cache-control"] == [
                    "no-cache"
                ]

            for target, content_types, body in (
                (
                    "/assets/index-D6dVqAIK.js",
                    ("application/javascript", "text/javascript"),
                    js_body,
                ),
                ("/assets/index-Abc123_9.css", ("text/css",), css_body),
            ):
                status, headers, encoded_body = _http_request_bytes(
                    port,
                    f"localhost:{caddy_port}",
                    target,
                    {"Accept-Encoding": "gzip"},
                )
                assert status == 200
                assert [value for key, value in headers if key.lower() == "cache-control"] == [
                    "public, max-age=31536000, immutable"
                ]
                assert [value for key, value in headers if key.lower() == "content-encoding"] == [
                    "gzip"
                ]
                assert any(
                    key.lower() == "vary" and "accept-encoding" in value.lower()
                    for key, value in headers
                )
                assert [value for key, value in headers if key.lower() == "content-type"][
                    0
                ] in content_types
                assert gzip.decompress(encoded_body) == body
                assert len(encoded_body) < len(body)

            status, headers, body = _http_request_bytes(
                port,
                f"localhost:{caddy_port}",
                "/assets/index-D6dVqAIK.js",
                {"If-Modified-Since": existing_last_modified, "Cache-Control": "no-cache"},
            )
            assert status == 200
            assert body == js_body
            assert [value for key, value in headers if key.lower() == "cache-control"] == [
                "public, max-age=31536000, immutable"
            ]
            status, headers, body = _http_request_bytes(
                port,
                f"localhost:{caddy_port}",
                "/assets/index-D6dVqAIK.js",
                {"If-None-Match": existing_etag, "Cache-Control": "no-cache"},
            )
            assert status == 200
            assert body == js_body
            assert [value for key, value in headers if key.lower() == "cache-control"] == [
                "public, max-age=31536000, immutable"
            ]

            for target in (
                "/assets/missing-D6dVqAIK.js",
                "/assets/missing.css",
            ):
                status, headers, body = _http_request_bytes(port, f"localhost:{caddy_port}", target)
                assert status == 404
                assert body != html_body
                assert [value for key, value in headers if key.lower() == "cache-control"] == [
                    "no-store"
                ]

            status, headers, body = _http_request_bytes(
                port,
                f"localhost:{caddy_port}",
                "/assets/missing-D6dVqAIK.js",
                {"If-Modified-Since": fallback_last_modified, "Cache-Control": "no-cache"},
            )
            assert status == 404
            assert body != html_body
            assert [value for key, value in headers if key.lower() == "cache-control"] == [
                "no-store"
            ]

            status, headers, body = _http_request_bytes(
                port,
                f"localhost:{caddy_port}",
                "/assets/missing-D6dVqAIK.js",
                {"If-None-Match": fallback_etag, "Cache-Control": "no-cache"},
            )
            assert status == 404
            assert body != html_body
            assert [value for key, value in headers if key.lower() == "cache-control"] == [
                "no-store"
            ]

            status, headers, _ = _http_request_bytes(
                port, f"localhost:{caddy_port}", "/assets/redirect-A1b2C3d4.js"
            )
            assert status == 302
            assert [value for key, value in headers if key.lower() == "location"] == [
                "/assets/index-D6dVqAIK.js"
            ]
            assert [value for key, value in headers if key.lower() == "cache-control"] == [
                "no-store"
            ]

            for target in ("/assets/logo.svg", "/api/health"):
                status, headers, _ = _http_request_bytes(port, f"localhost:{caddy_port}", target)
                assert status == 200
                assert [value for key, value in headers if key.lower() == "cache-control"] == [
                    "public, max-age=60"
                ]
        finally:
            subprocess.run(
                ["docker", "rm", "--force", container_name],
                check=False,
                capture_output=True,
                text=True,
            )
            upstream.shutdown()
            upstream.server_close()
            upstream_root.cleanup()


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
    assert (
        "CADDY_APP_SITE_HOSTS=${CADDY_APP_SITE_HOSTS:?CADDY_APP_SITE_HOSTS is required in production}"
        in src
    )
    assert (
        "CADDY_APP_REDIRECT_HOSTS=${CADDY_APP_REDIRECT_HOSTS:?CADDY_APP_REDIRECT_HOSTS is required in production}"
        in src
    )
    assert (
        "CADDY_APP_REDIRECT_ORIGIN=${CADDY_APP_REDIRECT_ORIGIN:?CADDY_APP_REDIRECT_ORIGIN is required in production}"
        in src
    )


def test_env_example_documents_comma_separated_cors_origins():
    src = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "FASTAPI_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173" in src
    assert 'FASTAPI_CORS_ORIGINS=["' not in src


def test_caddy_fail2ban_access_log_and_healthcheck_are_deployable():
    src = (ROOT / "Caddyfile.app").read_text(encoding="utf-8")
    entrypoint = (ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert "output file /data/access.log" in src
    assert "/data/logs/access.log" not in src
    assert "http://:80 {" in src
    assert "@health host localhost" in src
    assert 'respond "ok" 200' in src
    assert "auto_https disable_redirects" in entrypoint
    assert "import /etc/caddy/app.caddy" in entrypoint


def test_public_caddyfile_is_app_only_and_uses_deployment_redirect_settings():
    src = (ROOT / "Caddyfile.app").read_text(encoding="utf-8")

    assert "{$CADDY_APP_SITE_HOSTS:http://localhost:8080}" in src
    assert "@app_redirect_hosts host {$CADDY_APP_REDIRECT_HOSTS:localhost}" in src
    assert "redir {$CADDY_APP_REDIRECT_ORIGIN:https://localhost}{uri} 308" in src
    assert "172.28.0.1" not in src


def test_compose_does_not_pin_public_bridge_topology():
    src = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(src)

    assert "172.28." not in src
    assert "CADDY_APP_SITE_HOSTS=${CADDY_APP_SITE_HOSTS:-http://localhost:8080}" in src
    assert "CADDY_APP_REDIRECT_HOSTS=${CADDY_APP_REDIRECT_HOSTS:-localhost}" in src
    assert "CADDY_APP_REDIRECT_ORIGIN=${CADDY_APP_REDIRECT_ORIGIN:-https://localhost}" in src
    assert "./Caddyfile.app:/etc/caddy/app.caddy:ro" in src
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
