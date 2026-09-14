from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from ai_actuarial.api.client_ip import MAX_FORWARDED_HOPS, client_ip, validate_proxy_config
from ai_actuarial.api.middleware import rate_limit
from ai_actuarial.config import settings


@pytest.fixture(autouse=True)
def proxy_config(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "172.17.0.1/32,10.0.0.0/24,::1/128")


def request(peer, forwarded="", header=b"x-forwarded-for"):
    return Request(
        {
            "type": "http",
            "client": (peer, 12345) if peer else None,
            "headers": [(header, forwarded.encode())],
        }
    )


@pytest.mark.parametrize(
    "peer,forwarded,expected",
    [
        ("127.0.0.1", "203.0.113.1", "127.0.0.1"),
        ("::1", "", "::1"),
        (None, "203.0.113.1", "unknown"),
        ("testclient", "203.0.113.1", "testclient"),
        ("172.17.0.1", "203.0.113.1", "203.0.113.1"),
        ("172.17.0.1", "203.0.113.1, 10.0.0.2", "203.0.113.1"),
        ("172.17.0.1", "192.0.2.99, 203.0.113.1, 10.0.0.2", "203.0.113.1"),
        ("203.0.113.2", "192.0.2.99", "203.0.113.2"),
        ("::ffff:172.17.0.1", "::FFFF:203.0.113.1", "203.0.113.1"),
        ("::1", " 2001:DB8::AbCd , \t10.0.0.2 ", "2001:db8::abcd"),
        ("172.17.0.1", "10.0.0.2, 10.0.0.3", "10.0.0.2"),
        ("172.17.0.1", "203.0.113.1" + ",10.0.0.2" * MAX_FORWARDED_HOPS, "172.17.0.1"),
        (
            "172.17.0.1",
            "203.0.113.1" + ",10.0.0.2" * (MAX_FORWARDED_HOPS - 1),
            "203.0.113.1",
        ),
    ],
)
def test_client_ip_chain(peer, forwarded, expected):
    assert client_ip(request(peer, forwarded)) == expected


@pytest.mark.parametrize(
    "forwarded",
    [
        "",
        ",",
        " , , ",
        "203.0.113.1,",
        ",203.0.113.1",
        "unknown,203.0.113.1",
        "203.0.113.1:80",
        "[::1]",
        "fe80::1%eth0",
        "x" * 2100,
    ],
)
def test_malformed_chain_falls_back(forwarded):
    assert client_ip(request("172.17.0.1", forwarded)) == "172.17.0.1"


@pytest.mark.parametrize("cidrs", ["", " ", ",", "172.17.0.1/32,invalid", "172.17.0.1/33"])
def test_missing_or_invalid_allowlist_fails_closed(monkeypatch, caplog, cidrs):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", cidrs)
    validate_proxy_config()
    assert "forwarded headers will be ignored" in caplog.text
    assert client_ip(request("172.17.0.1", "203.0.113.1")) == "172.17.0.1"


@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "::ffff:172.17.0.1", "172.17.0.1", None])
def test_trust_disabled_preserves_socket_peer(monkeypatch, peer):
    monkeypatch.setattr(settings, "TRUST_PROXY", False)
    assert client_ip(request(peer, "203.0.113.1")) == (peer or "unknown")


def test_mapped_proxy_cidr(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_CIDRS", "::ffff:172.17.0.0/112")
    assert client_ip(request("172.17.0.1", "203.0.113.1")) == "203.0.113.1"


def test_duplicate_headers_keep_wire_order():
    req = request("172.17.0.1", "192.0.2.99")
    req.scope["headers"].append((b"x-forwarded-for", b"203.0.113.1,10.0.0.2"))
    assert client_ip(req) == "203.0.113.1"


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/register", "/api/chat/query"])
def test_clients_behind_same_proxy_have_independent_rate_limits(monkeypatch, path):
    monkeypatch.setattr(
        rate_limit, "AUTH_RATE_LIMIT_RULES", [rate_limit.RateLimitRule(1, 60, "minute")]
    )
    app = FastAPI()
    app.state.rate_limit_defaults = "1/minute"
    app.add_middleware(rate_limit.RateLimitMiddleware, store=rate_limit.RateLimitStore())

    @app.post(path)
    def endpoint(req: Request):
        return {"ip": client_ip(req)}

    with TestClient(app, client=("172.17.0.1", 12345)) as client:
        for ip in ["203.0.113.1", "203.0.113.2"]:
            headers = {"x-FoRwArDeD-fOr": ip}
            response = client.post(path, headers=headers)
            assert response.status_code == 200
            assert response.json() == {"ip": ip}
            assert client.post(path, headers=headers).status_code == 429


def test_server_preserves_socket_peer(monkeypatch):
    import uvicorn

    from ai_actuarial.api import app

    options = {}
    monkeypatch.setattr(app, "configure_application_logging", lambda **kwargs: None)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: options.update(kwargs))
    app.run_server()
    assert options["proxy_headers"] is False
