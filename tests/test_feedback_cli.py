from __future__ import annotations

import copy
import json
import subprocess
import sys
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from uuid import UUID

import pytest
import yaml

from ai_actuarial import cli
from ai_actuarial.feedback import inbox

CONTRACT = json.loads(
    (Path(__file__).parent / "fixtures/feedback_contract.json").read_text(encoding="utf-8")
)


def item(number=10, *, site="china", user=None, status="new"):
    record = copy.deepcopy(CONTRACT["admin_page"]["response"]["items"][0])
    record.update(
        id=number, feedback_id=str(UUID(int=number)), site_key=site, user_id=user, status=status
    )
    return record


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("FASTAPI_ENV", raising=False)
    monkeypatch.setenv("CHINA_FEEDBACK_TOKEN", "private-token")
    monkeypatch.setenv("OVERSEAS_FEEDBACK_TOKEN", "other-private-token")
    config = {
        "paths": {"data": str(tmp_path / "data")},
        "features": {"feedback_enabled": False},
        "feedback_inbox": {
            "sites": [
                {
                    "site_key": "china",
                    "url": "https://china.example",
                    "token_env": "CHINA_FEEDBACK_TOKEN",
                }
            ]
        },
    }
    path = tmp_path / "sites.yaml"

    def save():
        path.write_text(yaml.safe_dump(config), encoding="utf-8")

    save()
    return config, save, path, tmp_path / "data" / "feedback"


def run(setup, capsys, *args):
    parsed = cli.build_parser().parse_args(["--config", str(setup[2]), "feedback", *args, "--json"])
    code = parsed.func(parsed)
    output = capsys.readouterr()
    assert output.err == ""
    payload = json.loads(output.out)
    assert payload["schema_version"] == 1
    assert payload["command"] == args[0]
    assert payload["success"] is (code == 0)
    assert "private-token" not in output.out
    contract = json.loads(
        (Path(__file__).parent / "fixtures/feedback_cli_contract.json").read_text(encoding="utf-8")
    )
    assert sorted(payload) == contract["response_fields"]
    assert payload["outcome"] in contract["outcomes"]
    for row in payload["items"]:
        assert sorted(row) == contract["item_fields"]
    for result in payload["sites"]:
        assert sorted(result) == contract["site_fields"]
    assert output.out.isascii()
    return code, payload


def test_full_originals_pagination_idempotence_and_local_disabled_history(
    setup, monkeypatch, capsys
):
    rows = [item(10), item(11, user=42)]
    calls = []

    def request(site, *, cursor=None, feedback_id=None, status=None):
        calls.append((cursor, feedback_id, status))
        return {
            "items": rows[:1] if cursor == 0 else rows[1:],
            "next_cursor": 10 if cursor == 0 else None,
        }

    monkeypatch.setattr(inbox, "api_request", request)
    code, first = run(setup, capsys, "pull")
    assert code == 0 and first["sites"][0]["new_count"] == 2
    code, second = run(setup, capsys, "pull")
    assert code == 0 and second["outcome"] == "no_new_data"
    assert calls == [(0, None, None), (10, None, None)] * 2
    monkeypatch.setattr(inbox, "api_request", lambda *a, **k: pytest.fail("list must be local"))
    _, listed = run(setup, capsys, "list")
    assert listed["items"] == rows
    assert listed["sites"][0]["last_success_at"]
    text = (setup[3] / "inbox.md").read_text(encoding="utf-8")
    assert rows[0]["content"] in text and "42" in text
    assert "token_env" not in text and "https://china.example" not in text


def test_new_write_during_page_and_late_lower_commit_recovered(setup, monkeypatch, capsys):
    calls = []
    later = False

    def request(site, *, cursor=None, **kwargs):
        calls.append(cursor)
        if cursor == 0:
            return {"items": [item(5)] if later else [item(10)], "next_cursor": 5 if later else 10}
        if cursor == 5:
            return {"items": [item(10), item(20)], "next_cursor": None}
        return {"items": [item(20)], "next_cursor": None}

    monkeypatch.setattr(inbox, "api_request", request)
    assert run(setup, capsys, "pull")[0] == 0
    later = True
    assert run(setup, capsys, "pull")[0] == 0
    assert calls == [0, 10, 0, 5]
    assert [r["id"] for r in run(setup, capsys, "list")[1]["items"]] == [5, 10, 20]


def test_same_id_across_sites_and_one_site_outage_preserves_success(setup, monkeypatch, capsys):
    setup[0]["feedback_inbox"]["sites"].append(
        {
            "site_key": "overseas",
            "url": "https://overseas.example",
            "token_env": "OVERSEAS_FEEDBACK_TOKEN",
        }
    )
    setup[1]()
    fail = False

    def request(site, **kwargs):
        if fail and site["site_key"] == "overseas":
            raise inbox.InboxError("connection", "Connection failed")
        return {"items": [item(site=site["site_key"])], "next_cursor": None}

    monkeypatch.setattr(inbox, "api_request", request)
    assert run(setup, capsys, "pull")[0] == 0
    fail = True
    code, payload = run(setup, capsys, "pull")
    assert code == inbox.EXIT_CODES["connection"]
    assert payload["outcome"] == "partial_failure"
    assert payload["sites"][1]["last_success_at"]
    assert payload["sites"][1]["error"]["code"] == "connection"
    assert len(run(setup, capsys, "list")[1]["items"]) == 2
    assert run(setup, capsys, "mark", str(UUID(int=10)), "--status", "closed")[0] == 2


@pytest.mark.parametrize("problem", ["duplicate", "missing", "bad-url", "literal-token"])
def test_invalid_site_config_fails_before_network(setup, monkeypatch, capsys, problem):
    sites = setup[0]["feedback_inbox"]["sites"]
    if problem == "duplicate":
        sites.append(dict(sites[0]))
    elif problem == "missing":
        sites[0].pop("site_key")
    elif problem == "bad-url":
        sites[0]["url"] = "https://name:secret@example.com"
    else:
        sites[0]["token"] = "do-not-persist"
    setup[1]()
    monkeypatch.setattr(inbox, "api_request", lambda *a, **k: pytest.fail("invalid config"))
    code, payload = run(setup, capsys, "pull")
    assert code == 2 and payload["error"]["code"] == "config"


def test_page_atomic_failure_stops_before_next_page_and_retry_retains_prior(
    setup, monkeypatch, capsys
):
    monkeypatch.setattr(
        inbox, "api_request", lambda *a, **k: {"items": [item(1)], "next_cursor": None}
    )
    run(setup, capsys, "pull")
    before = (setup[3] / "inbox.json").read_bytes()
    calls = []

    def request(site, *, cursor=None, **kwargs):
        calls.append(cursor)
        return {"items": [item(2)], "next_cursor": 2}

    monkeypatch.setattr(inbox, "api_request", request)
    replace = inbox.os.replace

    def fail(source, target):
        if Path(target).name == "inbox.json":
            raise OSError("disk full private-token")
        return replace(source, target)

    monkeypatch.setattr(inbox.os, "replace", fail)
    code, payload = run(setup, capsys, "pull")
    assert code == inbox.EXIT_CODES["local_write"]
    assert payload["sites"][0]["error"]["code"] == "local_write"
    assert calls == [0]
    assert (setup[3] / "inbox.json").read_bytes() == before
    monkeypatch.setattr(inbox.os, "replace", replace)
    monkeypatch.setattr(
        inbox, "api_request", lambda *a, **k: {"items": [item(2)], "next_cursor": None}
    )
    assert run(setup, capsys, "pull")[0] == 0
    assert [r["id"] for r in run(setup, capsys, "list")[1]["items"]] == [1, 2]


def test_partial_page_outage_retry_starts_at_zero(setup, monkeypatch, capsys):
    calls = []

    def request(site, *, cursor=None, **kwargs):
        calls.append(cursor)
        if cursor:
            raise inbox.InboxError("connection", "Connection failed")
        return {"items": [item()], "next_cursor": 10}

    monkeypatch.setattr(inbox, "api_request", request)
    assert run(setup, capsys, "pull")[0] != 0
    assert len(run(setup, capsys, "list")[1]["items"]) == 1
    assert run(setup, capsys, "pull")[0] != 0
    assert calls == [0, 10, 0, 10]


def test_mark_authoritative_success_and_failure_keeps_previous_local_status(
    setup, monkeypatch, capsys
):
    monkeypatch.setattr(
        inbox, "api_request", lambda *a, **k: {"items": [item()], "next_cursor": None}
    )
    run(setup, capsys, "pull")
    server_item = item(status="closed")
    server_item["updated_at"] = "2026-11-05T13:00:00+00:00"
    calls = []

    def mark(site, *, feedback_id=None, status=None):
        calls.append((feedback_id, status))
        return server_item

    monkeypatch.setattr(inbox, "api_request", mark)
    code, result = run(setup, capsys, "mark", str(UUID(int=10)), "--status", "reviewed")
    assert code == 0 and result["items"] == [server_item]
    assert calls == [(str(UUID(int=10)), "reviewed")]
    before = (setup[3] / "inbox.json").read_bytes()

    def fail(*args, **kwargs):
        raise inbox.InboxError("authentication", "Invalid or expired management credential")

    monkeypatch.setattr(inbox, "api_request", fail)
    code, payload = run(setup, capsys, "mark", str(UUID(int=10)), "--status", "reviewed")
    assert code == inbox.EXIT_CODES["authentication"]
    assert payload["error"]["code"] == "authentication"
    assert (setup[3] / "inbox.json").read_bytes() == before


def test_empty_scan_keeps_marked_history_and_is_no_new_data(setup, monkeypatch, capsys):
    monkeypatch.setattr(
        inbox,
        "api_request",
        lambda *a, **k: {"items": [item(status="reviewed")], "next_cursor": None},
    )
    # Cache fixture is already reviewed; the live API normally filters this out.
    run(setup, capsys, "pull")
    monkeypatch.setattr(inbox, "api_request", lambda *a, **k: {"items": [], "next_cursor": None})
    code, payload = run(setup, capsys, "pull")
    assert code == 0 and payload["outcome"] == "no_new_data"
    assert run(setup, capsys, "list")[1]["items"][0]["status"] == "reviewed"


@pytest.mark.parametrize(
    "http,code", [(401, "authentication"), (403, "permission"), (503, "remote")]
)
def test_http_errors_and_secrets_are_not_echoed(setup, monkeypatch, capsys, http, code):
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://private-token.example", http, "private-token", {}, None
        )

    monkeypatch.setattr(inbox.urllib.request, "urlopen", fail)
    result, payload = run(setup, capsys, "pull")
    assert result == inbox.EXIT_CODES[code]
    assert payload["sites"][0]["error"]["code"] == code


def test_http_get_filters_and_patch_only_status(setup, monkeypatch, capsys):
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(
                {"items": [item()], "next_cursor": None}
                if len(requests) == 1
                else item(status="reviewed")
            ).encode()

    def open_request(request, *, timeout):
        requests.append(request)
        assert timeout == 30
        assert request.get_header("Authorization") == "Bearer private-token"
        return Response()

    monkeypatch.setattr(inbox.urllib.request, "urlopen", open_request)
    assert run(setup, capsys, "pull")[0] == 0
    assert requests[0].method == "GET"
    assert requests[0].full_url.endswith("?status=new&site_key=china&limit=100&cursor=0")
    assert run(setup, capsys, "mark", str(UUID(int=10)), "--status", "reviewed")[0] == 0
    assert requests[1].method == "PATCH"
    assert json.loads(requests[1].data) == {"status": "reviewed"}


@pytest.mark.parametrize("command", [[], ["pull"], ["list"], ["mark"]])
def test_help(command, capsys):
    with pytest.raises(SystemExit) as result:
        cli.build_parser().parse_args(["feedback", *command, "--help"])
    assert result.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_contract_fixture_has_stable_fields_and_exit_codes(setup, capsys):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/feedback_cli_contract.json").read_text(encoding="utf-8")
    )
    code, payload = run(setup, capsys, "list")
    assert code == 0
    assert sorted(payload) == fixture["response_fields"]
    assert inbox.EXIT_CODES == fixture["exit_codes"]
    schema = json.loads(
        (Path(__file__).parent / "fixtures/feedback_cli.schema.json").read_text(encoding="utf-8")
    )
    assert schema["required"] == fixture["response_fields"]
    assert schema["$defs"]["item"]["required"] == fixture["item_fields"]
    assert schema["$defs"]["site"]["required"] == fixture["site_fields"]


def test_real_competing_writer_returns_busy_without_changing_inbox(setup, monkeypatch, capsys):
    monkeypatch.setattr(
        inbox, "api_request", lambda *a, **k: {"items": [item()], "next_cursor": None}
    )
    run(setup, capsys, "pull")
    before = (setup[3] / "inbox.json").read_bytes()
    with inbox._lock(setup[3]):
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "ai_actuarial",
                "--config",
                str(setup[2]),
                "feedback",
                "pull",
                "--json",
            ],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        assert process.returncode == inbox.EXIT_CODES["busy"], process.stderr
        assert json.loads(process.stdout)["error"]["code"] == "busy"
        assert len(run(setup, capsys, "list")[1]["items"]) == 1
    assert (setup[3] / "inbox.json").read_bytes() == before


@pytest.mark.parametrize(
    "failure", [urllib.error.URLError("private-token"), TimeoutError("private-token")]
)
def test_connection_and_timeout_are_explicit(setup, monkeypatch, capsys, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(inbox.urllib.request, "urlopen", fail)
    code, payload = run(setup, capsys, "pull")
    assert code == inbox.EXIT_CODES["connection"]
    assert payload["sites"][0]["error"]["code"] == "connection"


def test_missing_credential_does_not_prevent_local_read(setup, monkeypatch, capsys):
    monkeypatch.delenv("CHINA_FEEDBACK_TOKEN")
    code, payload = run(setup, capsys, "pull")
    assert code == inbox.EXIT_CODES["authentication"]
    assert "credential" in payload["sites"][0]["error"]["message"].lower()
    assert run(setup, capsys, "list")[0] == 0


@pytest.mark.parametrize(
    "page",
    [
        {"items": [item()], "next_cursor": 0},
        {"items": [item(), item(9)], "next_cursor": None},
        {"items": [item(site="overseas")], "next_cursor": None},
        {"items": [{"feedback_id": str(UUID(int=1))}], "next_cursor": None},
        {"items": [], "next_cursor": 1},
        {"items": None, "next_cursor": None},
        [],
    ],
)
def test_malformed_or_wrong_identity_page_is_not_applied(setup, monkeypatch, capsys, page):
    monkeypatch.setattr(inbox, "api_request", lambda *a, **k: page)
    code, result = run(setup, capsys, "pull")
    assert code == inbox.EXIT_CODES["protocol"]
    assert result["sites"][0]["new_count"] == 0
    assert not (setup[3] / "inbox.json").exists()


@pytest.mark.parametrize(
    "filename,content",
    [
        ("inbox.json", "{broken"),
        ("inbox.json", '{"schema_version":1,"items":[{}]}'),
        ("sync.json", '{"schema_version":1,"sites":{"china":null}}'),
    ],
)
def test_corrupt_local_files_fail_without_overwriting(
    setup, monkeypatch, capsys, filename, content
):
    setup[3].mkdir(parents=True)
    path = setup[3] / filename
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        inbox, "api_request", lambda *a, **k: pytest.fail("do not overwrite invalid local data")
    )
    assert run(setup, capsys, "pull")[0] == inbox.EXIT_CODES["local_read"]
    assert run(setup, capsys, "list")[0] == inbox.EXIT_CODES["local_read"]
    assert path.read_text(encoding="utf-8") == content


def test_report_failure_retains_canonical_record_and_next_scan_repairs_report(
    setup, monkeypatch, capsys
):
    row = item()
    row["content"] = "Original line one\n```\nOriginal line two"
    monkeypatch.setattr(inbox, "api_request", lambda *a, **k: {"items": [row], "next_cursor": None})
    replace = inbox.os.replace

    def fail(source, target):
        if Path(target).name == "inbox.md":
            raise OSError("report write failure")
        return replace(source, target)

    monkeypatch.setattr(inbox.os, "replace", fail)
    assert run(setup, capsys, "pull")[0] == inbox.EXIT_CODES["local_write"]
    assert run(setup, capsys, "list")[1]["items"] == [row]
    monkeypatch.setattr(inbox.os, "replace", replace)
    assert run(setup, capsys, "pull")[0] == 0
    assert row["content"] in (setup[3] / "inbox.md").read_text(encoding="utf-8")


def test_mark_qualified_site_changes_only_that_site(setup, monkeypatch, capsys):
    setup[0]["feedback_inbox"]["sites"].append(
        {
            "site_key": "overseas",
            "url": "https://overseas.example",
            "token_env": "OVERSEAS_FEEDBACK_TOKEN",
        }
    )
    setup[1]()
    monkeypatch.setattr(
        inbox,
        "api_request",
        lambda site, **k: {"items": [item(site=site["site_key"])], "next_cursor": None},
    )
    run(setup, capsys, "pull")
    monkeypatch.setattr(
        inbox, "api_request", lambda site, **k: item(site=site["site_key"], status="closed")
    )
    assert (
        run(
            setup, capsys, "mark", str(UUID(int=10)), "--site-key", "overseas", "--status", "closed"
        )[0]
        == 0
    )
    rows = run(setup, capsys, "list")[1]["items"]
    assert [(row["site_key"], row["status"]) for row in rows] == [
        ("china", "new"),
        ("overseas", "closed"),
    ]


def test_second_site_keeps_first_sites_json_when_first_report_write_fails(
    setup, monkeypatch, capsys
):
    setup[0]["feedback_inbox"]["sites"].append(
        {
            "site_key": "overseas",
            "url": "https://overseas.example",
            "token_env": "OVERSEAS_FEEDBACK_TOKEN",
        }
    )
    setup[1]()
    monkeypatch.setattr(
        inbox,
        "api_request",
        lambda site, **k: {"items": [item(site=site["site_key"])], "next_cursor": None},
    )
    replace = inbox.os.replace
    failed = False

    def fail_once(source, target):
        nonlocal failed
        if not failed and Path(target).name == "inbox.md":
            failed = True
            raise OSError("first report failure")
        return replace(source, target)

    monkeypatch.setattr(inbox.os, "replace", fail_once)
    code, payload = run(setup, capsys, "pull")
    assert code == inbox.EXIT_CODES["local_write"]
    assert payload["outcome"] == "partial_failure"
    assert len(run(setup, capsys, "list")[1]["items"]) == 2


@pytest.mark.parametrize(
    "arguments",
    [
        ["mark", str(UUID(int=10)), "--status", "invalid"],
        ["mark", "--status", "closed"],
        ["list", "--unknown", "private-token"],
        [],
    ],
)
def test_json_usage_errors_have_stable_stdout(arguments, capsys):
    with pytest.raises(SystemExit) as result:
        cli.build_parser().parse_args(["feedback", *arguments, "--json"])
    output = capsys.readouterr()
    assert result.value.code == 2
    assert output.err == ""
    payload = json.loads(output.out)
    assert payload["success"] is False
    assert payload["error"]["code"] == "config"
    assert "private-token" not in output.out


def test_truncated_http_body_is_site_failure_and_next_site_still_succeeds(setup, capsys):
    truncate = False

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            site = "china" if self.path.startswith("/china/") else "overseas"
            body = json.dumps(
                {"items": [item(20 if truncate else 10, site=site)], "next_cursor": None}
            ).encode()
            broken = truncate and site == "china"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body) + 100 if broken else len(body)))
            self.end_headers()
            self.wfile.write(body[:10] if broken else body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        setup[0]["feedback_inbox"]["sites"] = [
            {
                "site_key": site,
                "url": f"{base}/{site}",
                "token_env": f"{site.upper()}_FEEDBACK_TOKEN",
            }
            for site in ("china", "overseas")
        ]
        setup[1]()
        _, first = run(setup, capsys, "pull")
        assert first["success"]
        prior_success = first["sites"][0]["last_success_at"]
        truncate = True
        code, payload = run(setup, capsys, "pull")
        assert code == inbox.EXIT_CODES["connection"]
        assert payload["outcome"] == "partial_failure"
        assert payload["sites"][0]["error"]["code"] == "connection"
        assert payload["sites"][0]["last_success_at"] == prior_success
        assert payload["sites"][1]["success"]
        rows = run(setup, capsys, "list")[1]["items"]
        assert [(row["site_key"], row["id"]) for row in rows] == [
            ("china", 10),
            ("overseas", 10),
            ("overseas", 20),
        ]
        report = (setup[3] / "inbox.md").read_text(encoding="utf-8")
        assert "china: outcome=failed" in report
        assert "overseas: outcome=updated" in report
        assert "error=connection" in report and prior_success in report
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize(
    "filename,report_exists", [("inbox.md", True), ("inbox.json", True), ("inbox.json", False)]
)
def test_failed_mark_local_write_preserves_exact_canonical_and_report(
    setup, monkeypatch, capsys, filename, report_exists
):
    monkeypatch.setattr(
        inbox, "api_request", lambda *a, **k: {"items": [item()], "next_cursor": None}
    )
    run(setup, capsys, "pull")
    if not report_exists:
        (setup[3] / "inbox.md").unlink()
    before = {
        name: (setup[3] / name).read_bytes()
        for name in ("inbox.json", "inbox.md")
        if (setup[3] / name).exists()
    }
    monkeypatch.setattr(inbox, "api_request", lambda *a, **k: item(status="closed"))
    replace = inbox.os.replace

    def fail(source, target):
        if Path(target).name == filename:
            raise OSError("mark write failure")
        return replace(source, target)

    monkeypatch.setattr(inbox.os, "replace", fail)
    code, payload = run(setup, capsys, "mark", str(UUID(int=10)), "--status", "closed")
    assert code == inbox.EXIT_CODES["local_write"]
    assert payload["error"]["code"] == "local_write"
    assert run(setup, capsys, "list")[1]["items"][0]["status"] == "new"
    for name, prior in before.items():
        assert (setup[3] / name).read_bytes() == prior
    if not report_exists:
        assert not (setup[3] / "inbox.md").exists()


def test_human_views_show_cached_sync_success_and_failure(setup, monkeypatch, capsys):
    monkeypatch.setattr(
        inbox, "api_request", lambda *a, **k: {"items": [item()], "next_cursor": None}
    )
    _, result = run(setup, capsys, "pull")
    last_success = result["sites"][0]["last_success_at"]

    def assert_views(outcome, error):
        args = cli.build_parser().parse_args(["--config", str(setup[2]), "feedback", "list"])
        assert args.func(args) == 0
        text = capsys.readouterr().out
        report = (setup[3] / "inbox.md").read_text(encoding="utf-8")
        for view in (text, report):
            assert "local cached" in view.lower()
            assert "china" in view
            assert last_success in view
            assert outcome in view
            if error:
                assert error in view

    assert_views("updated", None)

    def fail(*a, **k):
        raise inbox.InboxError("connection", "Feedback API connection failed")

    monkeypatch.setattr(inbox, "api_request", fail)
    assert run(setup, capsys, "pull")[0] == inbox.EXIT_CODES["connection"]
    assert_views("failed", "connection")
