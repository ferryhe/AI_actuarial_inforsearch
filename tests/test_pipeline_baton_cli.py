from __future__ import annotations

import json
import math
import urllib.error
from typing import Any

import pytest

from ai_actuarial import cli


def test_pipeline_cli_status_start_tick_and_config_use_same_http_contract(monkeypatch, capsys) -> None:
    calls: list[tuple[str, str]] = []

    def request(api_url: str, action: str, *, method: str, token: str | None):
        calls.append((action, method))
        return {"action": action, "round_status": "running"}

    monkeypatch.setattr(cli, "pipeline_api_request", request)
    parser = cli.build_parser()

    for argv in (
        ["pipeline", "status", "--json"],
        ["pipeline", "start", "--json"],
        ["pipeline", "tick", "--json"],
        ["pipeline", "config", "--json"],
    ):
        args = parser.parse_args(argv)
        assert args.func(args) == 0
        assert json.loads(capsys.readouterr().out)["action"] == argv[1]

    assert calls == [
        ("status", "GET"),
        ("start", "POST"),
        ("tick", "POST"),
        ("config", "GET"),
    ]

    with pytest.raises(SystemExit):
        parser.parse_args(["pipeline", "config", "--overrides", "{}"])


def test_pipeline_api_request_preserves_bearer_token_and_uses_finite_timeout(
    monkeypatch, capsys
) -> None:
    captured: dict[str, Any] = {}
    token = "real-secret-token"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b'{"success": true}'

    def urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(cli.urllib.request, "urlopen", urlopen)

    assert cli.pipeline_api_request(
        "https://api.example", "status", method="GET", token=token
    ) == {"success": True}
    request = captured["request"]
    assert request.get_header("Authorization") == f"Bearer {token}"
    assert isinstance(captured["timeout"], (int, float))
    assert math.isfinite(captured["timeout"])
    assert captured["timeout"] > 0
    output = capsys.readouterr()
    assert token not in output.out
    assert token not in output.err


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("Pipeline API returned HTTP 503: unavailable"),
        urllib.error.URLError("connection refused"),
    ],
)
def test_pipeline_cli_json_failures_are_machine_readable_and_nonzero(
    monkeypatch, capsys, failure: Exception
) -> None:
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(cli, "pipeline_api_request", fail)
    args = cli.build_parser().parse_args(["pipeline", "status", "--json"])

    assert args.func(args) != 0
    assert json.loads(capsys.readouterr().out) == {
        "error": str(failure),
        "success": False,
    }
