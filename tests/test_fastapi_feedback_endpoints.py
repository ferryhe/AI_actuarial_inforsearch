from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg2
import pytest
import yaml
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from ai_actuarial.api.app import create_app
from ai_actuarial.api.deps import AuthContext
from ai_actuarial.api.middleware import rate_limit
from ai_actuarial.features.assistant import feature as host
from ai_actuarial.feedback import inbox
from ai_actuarial.feedback.store import list_feedback
from ai_actuarial.shared_auth import hash_token, permissions_for_group
from ai_actuarial.shared_runtime import resolve_runtime_features
from ai_actuarial.skills.feedback.executors import draft
from ai_actuarial.storage import Storage
from tests.postgres_helpers import postgres_url_for_path


@pytest.fixture
def feedback_client(tmp_path, monkeypatch):
    database = postgres_url_for_path(tmp_path / "feedback")
    config = tmp_path / "sites.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "sites": [],
                "scheduled_tasks": [],
                "paths": {"download_dir": str(tmp_path / "files")},
                "features": {
                    "feedback_enabled": True,
                    "feedback_site_key": "site-test",
                    "feedback_rate_limit": "100 per minute",
                    "enable_rate_limiting": False,
                    "enable_csrf": False,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "feedback-test-session-secret")
    for name in (
        "FEEDBACK_ENABLED",
        "ASSISTANT_ENABLED",
        "FEEDBACK_SITE_KEY",
        "FEEDBACK_RATE_LIMIT",
        "ENABLE_CSRF",
        "ENABLE_RATE_LIMITING",
        "RATE_LIMIT_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    storage = Storage(database)
    try:
        user_id = storage.create_user(
            "feedback@example.test", "synthetic-password-hash", role="registered"
        )
        for role in ("registered", "admin"):
            storage.upsert_auth_token_by_hash(
                subject=f"feedback-{role}",
                group_name=role,
                token_hash=hash_token(f"feedback-{role}"),
                is_active=True,
            )
    finally:
        storage.close()
    for store in rate_limit._rate_limit_stores.values():
        store._buckets.clear()
    app = create_app()
    with TestClient(app) as client:
        yield client, app, database, user_id


def _request(**values):
    return {"client_request_id": str(uuid4()), "content": "网站建议", **values}


def _admin():
    return {"X-API-Token": "feedback-admin"}


def test_anonymous_and_logged_submission_use_server_identity_and_site(feedback_client):
    client, app, database, user_id = feedback_client
    anonymous = client.post(
        "/api/feedback",
        json=_request(
            user_id=99999,
            site_key="forged",
            content="  保留用户原文  ",
            page_path="/files?q=secret#hash",
        ),
    )
    assert anonymous.status_code == 201, anonymous.text
    cookie = URLSafeSerializer(app.state.fastapi_session_secret, salt="fastapi-session").dumps(
        {"email_user_id": user_id}
    )
    client.cookies.set("session", cookie)
    authenticated = client.post("/api/feedback", json=_request(user_id=99999, site_key="forged"))
    assert authenticated.status_code == 201, authenticated.text
    rows = list_feedback(database)["items"]
    assert [(row["user_id"], row["site_key"]) for row in rows] == [
        (None, "site-test"),
        (user_id, "site-test"),
    ]
    assert rows[0]["content"] == "保留用户原文" and rows[0]["page_path"] == "/files"
    assert set(anonymous.json()) == {"feedback_id", "status", "created_at"}
    assert anonymous.json()["status"] == "recorded"
    assert anonymous.json()["created_at"].endswith("+00:00")


def test_idempotent_retries_conflict_and_distinct_keys(feedback_client):
    client, _, database, _ = feedback_client
    payload = _request()
    first = client.post("/api/feedback", json=payload)
    replay = client.post("/api/feedback", json=payload)
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    conflict = client.post("/api/feedback", json={**payload, "content": "不同"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert client.post("/api/feedback", json=_request()).status_code == 201
    assert len(list_feedback(database)["items"]) == 2


@pytest.mark.parametrize(
    "values",
    [
        {"content": ""},
        {"content": " \t\n "},
        {"content": "字" * 4001},
        {"content": 123},
        {"content": None},
        {"content": "bad\x00text"},
        {"kind": "invalid"},
        {"origin": "chat"},
        {"client_request_id": "not-uuid"},
        {"page_path": "https://example.test/private?q=secret"},
        {"page_path": "//example.test/path"},
        {"page_path": "/\\example.test"},
        {"page_path": "/path\nheader"},
        {"page_path": "/" * 2049},
        {"page_path": None},
        {"locale": "x" * 36},
        {"locale": 123},
    ],
)
def test_input_boundaries_reject_without_writes(feedback_client, values):
    client, _, database, _ = feedback_client
    response = client.post("/api/feedback", json=_request(**values))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert list_feedback(database)["items"] == []


@pytest.mark.parametrize("content", ["字", "字" * 4000])
def test_content_inclusive_length_bounds(feedback_client, content):
    client, _, database, _ = feedback_client
    assert client.post("/api/feedback", json=_request(content=content)).status_code == 201
    assert list_feedback(database)["items"][0]["content"] == content


def test_database_commit_failure_has_no_success_receipt_or_row(feedback_client):
    client, _, database, _ = feedback_client
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        cursor.execute(
            "CREATE FUNCTION reject_feedback_commit() RETURNS trigger LANGUAGE plpgsql "
            "AS $$ BEGIN RAISE EXCEPTION 'synthetic commit failure'; END $$"
        )
        cursor.execute(
            "CREATE CONSTRAINT TRIGGER reject_commit AFTER INSERT ON feedback_items "
            "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            "EXECUTE FUNCTION reject_feedback_commit()"
        )
    payload = _request()
    response = client.post("/api/feedback", json=payload)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FEEDBACK_UNAVAILABLE"
    assert "feedback_id" not in response.json()
    assert list_feedback(database)["items"] == []
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER reject_commit ON feedback_items")
    assert client.post("/api/feedback", json=payload).status_code == 201
    assert len(list_feedback(database)["items"]) == 1


@pytest.mark.parametrize(
    "headers,expected", [({}, 401), ({"X-API-Token": "feedback-registered"}, 403)]
)
def test_admin_endpoints_force_auth_even_when_public_browse_enabled(
    feedback_client, headers, expected
):
    client, app, _, _ = feedback_client
    app.state.require_auth = False
    assert client.get("/api/admin/feedback", headers=headers).status_code == expected
    assert (
        client.patch(
            f"/api/admin/feedback/{uuid4()}", json={"status": "reviewed"}, headers=headers
        ).status_code
        == expected
    )
    for role in ("guest", "registered", "premium", "operator"):
        assert not {"feedback.read", "feedback.manage"} & permissions_for_group(role)
    assert {"feedback.read", "feedback.manage"} <= permissions_for_group("admin")


def test_admin_filters_keyset_and_status_only_update_preserve_text(feedback_client):
    client, _, database, _ = feedback_client
    ids = [
        client.post("/api/feedback", json=_request(content=f"原文 {i}")).json()["feedback_id"]
        for i in range(7)
    ]
    with psycopg2.connect(database) as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE feedback_items SET created_at = '2026-01-01T00:00:00Z'")
        cursor.execute(
            "UPDATE feedback_items SET site_key = 'site-other' WHERE feedback_id = %s", (ids[-1],)
        )
    traversed, after = [], 0
    while True:
        response = client.get(
            "/api/admin/feedback", params={"limit": 2, "cursor": after}, headers=_admin()
        )
        assert response.status_code == 200, response.text
        page = response.json()
        traversed.extend(item["feedback_id"] for item in page["items"])
        if page["next_cursor"] is None:
            break
        assert page["next_cursor"] > after
        after = page["next_cursor"]
    assert traversed == ids and len(set(traversed)) == 7
    for status in ("reviewed", "closed", "new"):
        response = client.patch(
            f"/api/admin/feedback/{ids[0]}", json={"status": status}, headers=_admin()
        )
        assert response.status_code == 200 and response.json()["status"] == status
        assert response.json()["content"] == "原文 0"
    response = client.get(
        "/api/admin/feedback", params={"site_key": "site-test", "status": "new"}, headers=_admin()
    )
    assert len(response.json()["items"]) == 6
    blocked = client.patch(
        f"/api/admin/feedback/{ids[0]}",
        json={"status": "closed", "content": "rewrite"},
        headers=_admin(),
    )
    assert blocked.status_code == 422
    assert list_feedback(database)["items"][0]["content"] == "原文 0"
    assert (
        client.patch(
            f"/api/admin/feedback/{uuid4()}", json={"status": "closed"}, headers=_admin()
        ).status_code
        == 404
    )
    for params in (
        {"cursor": -1},
        {"cursor": "bad"},
        {"limit": 0},
        {"limit": 101},
        {"status": "bad"},
    ):
        assert client.get("/api/admin/feedback", params=params, headers=_admin()).status_code == 422


def test_feedback_rate_limit_is_enforced_with_global_limiting_off(feedback_client):
    client, app, database, _ = feedback_client
    app.state.feedback_rate_limit = "1 per minute"
    app.state.enable_rate_limiting = False
    assert client.post("/api/feedback", json=_request()).status_code == 201
    response = client.post("/api/feedback", json=_request())
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert int(response.headers["Retry-After"]) > 0
    assert len(list_feedback(database)["items"]) == 1


def test_feedback_rate_limit_configuration_has_a_finite_ceiling(feedback_client):
    client, app, _, _ = feedback_client
    app.state.feedback_rate_limit = "1000000 per minute"
    response = client.post("/api/feedback", json=_request())
    assert response.status_code == 201
    assert response.headers["X-RateLimit-Limit"] == "1000"


def test_feedback_uses_existing_csrf_protection(feedback_client):
    client, app, database, _ = feedback_client
    app.state.enable_csrf = True
    assert client.post("/api/feedback", json=_request()).status_code == 403
    response = client.get("/api/support/capabilities")
    csrf = response.cookies["csrf_token"]
    assert (
        client.post("/api/feedback", json=_request(), headers={"X-CSRF-Token": csrf}).status_code
        == 201
    )
    assert len(list_feedback(database)["items"]) == 1


def test_feedback_rate_limit_uses_trusted_proxy_and_ignores_untrusted_headers(
    feedback_client, monkeypatch
):
    _, app, database, _ = feedback_client
    app.state.feedback_rate_limit = "1 per minute"
    monkeypatch.setattr(rate_limit.settings, "TRUST_PROXY", True)
    monkeypatch.setattr(rate_limit.settings, "TRUSTED_PROXY_CIDRS", "172.17.0.1/32")
    with TestClient(app, client=("172.17.0.1", 12345)) as trusted:
        for ip in ("203.0.113.10", "203.0.113.11"):
            assert (
                trusted.post(
                    "/api/feedback", json=_request(), headers={"X-Forwarded-For": ip}
                ).status_code
                == 201
            )
        assert (
            trusted.post(
                "/api/feedback", json=_request(), headers={"X-Forwarded-For": "203.0.113.10"}
            ).status_code
            == 429
        )
    with TestClient(app, client=("198.51.100.1", 12345)) as untrusted:
        assert (
            untrusted.post(
                "/api/feedback", json=_request(), headers={"X-Forwarded-For": "203.0.113.20"}
            ).status_code
            == 201
        )
        assert (
            untrusted.post(
                "/api/feedback", json=_request(), headers={"X-Forwarded-For": "203.0.113.21"}
            ).status_code
            == 429
        )
    assert len(list_feedback(database)["items"]) == 3


@pytest.mark.parametrize("rule", ["", "invalid", "0 per minute"])
def test_invalid_feedback_rate_limit_keeps_bounded_default(feedback_client, rule):
    client, app, database, _ = feedback_client
    app.state.feedback_rate_limit = rule
    for _ in range(5):
        assert client.post("/api/feedback", json=_request()).status_code == 201
    assert client.post("/api/feedback", json=_request()).status_code == 429
    assert len(list_feedback(database)["items"]) == 5


def test_switches_apply_after_app_restart_and_preserve_history(feedback_client, monkeypatch):
    client, _, database, _ = feedback_client
    assert client.post("/api/feedback", json=_request()).status_code == 201
    before = list_feedback(database)
    monkeypatch.setenv("FEEDBACK_ENABLED", "false")
    monkeypatch.setenv("ASSISTANT_ENABLED", "true")
    with TestClient(create_app()) as disabled:
        assert disabled.get("/api/support/capabilities").json() == {
            "feedback_enabled": False,
            "assistant_enabled": True,
        }
        assert disabled.post("/api/feedback", json=_request()).status_code == 404
        assert disabled.get("/api/admin/feedback", headers=_admin()).json() == before
    monkeypatch.setenv("FEEDBACK_ENABLED", "true")
    with TestClient(create_app()) as reopened:
        assert reopened.get("/api/support/capabilities").json() == {
            "feedback_enabled": True,
            "assistant_enabled": True,
        }
        assert reopened.get("/api/admin/feedback", headers=_admin()).json() == before
    monkeypatch.setenv("FEEDBACK_SITE_KEY", "https://forged.example")
    with pytest.raises(ValueError, match="feedback_site_key"):
        create_app()


def test_disabled_and_reopened_feedback_retains_admin_history_and_truthful_capabilities(
    feedback_client,
):
    client, app, database, _ = feedback_client
    assert client.post("/api/feedback", json=_request()).status_code == 201
    before = list_feedback(database)
    for feedback, assistant in ((False, False), (True, False), (False, True), (True, True)):
        app.state.feedback_enabled = feedback
        app.state.assistant_enabled = assistant
        assert (
            resolve_runtime_features({"features": {"assistant_enabled": assistant}})[
                "assistant_enabled"
            ]
            == assistant
        )
        assert client.get("/api/support/capabilities").json() == {
            "feedback_enabled": feedback,
            "assistant_enabled": assistant,
        }
    app.state.feedback_enabled = False
    app.state.enable_csrf = True
    response = client.post("/api/feedback", json=_request())
    assert response.status_code == 404 and response.json()["error"]["code"] == "FEATURE_DISABLED"
    malformed = client.post(
        "/api/feedback", content="not json", headers={"Content-Type": "application/json"}
    )
    assert malformed.status_code == 404 and malformed.json() == response.json()
    assert client.get("/api/admin/feedback", headers=_admin()).status_code == 200
    assert (
        client.patch(
            f"/api/admin/feedback/{before['items'][0]['feedback_id']}",
            json={"status": "reviewed"},
            headers=_admin(),
        ).status_code
        == 200
    )
    app.state.feedback_enabled = True
    assert list_feedback(database)["items"][0]["feedback_id"] == before["items"][0]["feedback_id"]
    assert list_feedback(database)["items"][0]["content"] == before["items"][0]["content"]


def test_support_flags_default_off_yaml_then_env_priority(monkeypatch):
    for name in (
        "FEEDBACK_ENABLED",
        "ASSISTANT_ENABLED",
        "FEEDBACK_SITE_KEY",
        "FEEDBACK_RATE_LIMIT",
    ):
        monkeypatch.delenv(name, raising=False)
    default = resolve_runtime_features({})
    assert default["feedback_enabled"] is default["assistant_enabled"] is False
    yaml_features = {
        "feedback_enabled": True,
        "assistant_enabled": True,
        "feedback_site_key": "yaml-site",
        "feedback_rate_limit": "2 per minute",
    }
    result = resolve_runtime_features({"features": yaml_features})
    assert all(result[key] == value for key, value in yaml_features.items())
    monkeypatch.setenv("FEEDBACK_ENABLED", "false")
    monkeypatch.setenv("ASSISTANT_ENABLED", "false")
    monkeypatch.setenv("FEEDBACK_SITE_KEY", "env-site")
    monkeypatch.setenv("FEEDBACK_RATE_LIMIT", "3 per minute")
    result = resolve_runtime_features({"features": yaml_features})
    assert result["feedback_enabled"] is result["assistant_enabled"] is False
    assert (
        result["feedback_site_key"] == "env-site"
        and result["feedback_rate_limit"] == "3 per minute"
    )
    assert all(result["feature_sources"][key] == "env" for key in yaml_features)


def test_fixed_consumer_request_and_error_fixtures(feedback_client):
    client, app, _, _ = feedback_client
    fixtures = json.loads(Path("tests/fixtures/feedback_contract.json").read_text(encoding="utf-8"))
    response = client.post("/api/feedback", json=fixtures["submission"]["request"])
    assert response.status_code == fixtures["submission"]["status"]
    assert set(response.json()) == set(fixtures["submission"]["receipt"])
    page = client.get("/api/admin/feedback", headers=_admin()).json()
    assert set(page) == set(fixtures["admin_page"]["response"])
    assert set(page["items"][0]) == set(fixtures["admin_page"]["response"]["items"][0])
    assert page["next_cursor"] is None
    conflict = client.post(
        "/api/feedback", json={**fixtures["submission"]["request"], "content": "changed"}
    )
    assert conflict.json() == fixtures["errors"]["idempotency_conflict"]
    invalid = client.post(
        "/api/feedback", json={**fixtures["submission"]["request"], "content": ""}
    )
    assert invalid.json() == fixtures["errors"]["invalid_request"]
    app.state.feedback_enabled = False
    assert (
        client.post("/api/feedback", json=fixtures["submission"]["request"]).json()
        == fixtures["errors"]["feature_disabled"]
    )


def test_issue478_host_draft_edit_confirm_receipt_local_pull_and_review(
    feedback_client, tmp_path, monkeypatch
):
    client, _app, database, _user_id = feedback_client
    original = "Please show source dates 中文"

    class HostStorage:
        def __init__(self, database):
            assert database == "host-feedback-fixture"

        def close(self):
            pass

    with monkeypatch.context() as isolated:
        isolated.setattr(host.chat, "Storage", HostStorage)
        isolated.setattr(host.chat, "_resolve_chat_user", lambda *_: ("test", None))
        isolated.setattr(host.chat, "_enforce_chat_quota", lambda **_: None)
        auth = AuthContext({"subject": "user"}, frozenset({"chat.query"}))
        isolated.setattr(host.deps, "get_auth_context", lambda request: auth)
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(db_path="host-feedback-fixture", feedback_enabled=True)
            ),
            state=SimpleNamespace(),
        )
        evidence_id = draft({"text": original}).evidence_ids[0]
        outputs = iter(
            [
                json.dumps(
                    {
                        "action": "call",
                        "skill_id": "feedback",
                        "tool_id": "feedback.draft",
                        "args": {"text": "model rewrite"},
                    }
                ),
                json.dumps(
                    {"action": "finish", "answer": "Already sent", "evidence_ids": [evidence_id]}
                ),
            ]
        )
        outcome = host.AssistantFeature().query(
            request=request, auth=auth, message=original, model=lambda *_: next(outputs)
        )
    assert outcome.runtime.kind == "finish"
    assert outcome.response.intent == "feedback"
    assert outcome.response.feedback_draft == original
    assert "nothing is recorded yet" in outcome.response.answer
    assert list_feedback(database)["items"] == []

    edited = original + " — please include source names"

    def submit(confirmed):
        return (
            client.post(
                "/api/feedback",
                json=_request(content=edited, origin="widget", page_path="/weekly"),
            )
            if confirmed
            else None
        )

    assert submit(False) is None
    assert list_feedback(database)["items"] == []
    response = submit(True)
    assert response.status_code == 201 and response.json()["status"] == "recorded"
    feedback_id = response.json()["feedback_id"]
    recorded = list_feedback(database)["items"][0]
    assert (
        recorded["feedback_id"],
        recorded["content"],
        recorded["site_key"],
        recorded["origin"],
    ) == (feedback_id, edited, "site-test", "widget")
    site = {"site_key": "site-test", "url": "http://local.test", "token_env": "TASK_TOKEN"}

    def api_request(_site, *, cursor=None, feedback_id=None, status=None):
        if feedback_id is not None:
            reply = client.patch(
                f"/api/admin/feedback/{feedback_id}", json={"status": status}, headers=_admin()
            )
        else:
            reply = client.get(
                "/api/admin/feedback",
                params={"status": "new", "site_key": "site-test", "cursor": cursor},
                headers=_admin(),
            )
        assert reply.status_code == 200
        return reply.json()

    monkeypatch.setattr(inbox, "api_request", api_request)
    root = tmp_path / "local-feedback"
    first = {"sites": [], "items": [], "outcome": "listed"}
    assert inbox._pull(root, [site], first) == 0
    assert first["sites"][0]["new_count"] == 1
    second = {"sites": [], "items": [], "outcome": "listed"}
    assert inbox._pull(root, [site], second) == 0
    assert second["outcome"] == "no_new_data"
    before = next(iter(inbox._load(root).values()))
    assert (before["feedback_id"], before["site_key"], before["content"], before["origin"]) == (
        feedback_id,
        "site-test",
        edited,
        "widget",
    )
    marked = {"sites": [], "items": [], "outcome": "listed"}
    assert (
        inbox._mark(
            root,
            [site],
            SimpleNamespace(feedback_id=feedback_id, status="reviewed", site_key="site-test"),
            marked,
        )
        == 0
    )
    after = next(iter(inbox._load(root).values()))
    assert after["status"] == "reviewed"
    assert (after["feedback_id"], after["site_key"], after["content"], after["origin"]) == (
        feedback_id,
        "site-test",
        edited,
        "widget",
    )
    assert (
        list_feedback(database, status="reviewed", site_key="site-test")["items"][0]["feedback_id"]
        == feedback_id
    )
