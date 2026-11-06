from __future__ import annotations

import subprocess
import sys
from uuid import uuid4

import pytest

from ai_actuarial.assistant import router
from ai_actuarial.assistant.query import QueryResponse
from ai_actuarial.shared_runtime import resolve_runtime_features

pytest_plugins = ("tests.test_fastapi_feedback_endpoints",)


@pytest.mark.parametrize(
    "assistant,feedback", [(False, False), (False, True), (True, False), (True, True)]
)
def test_independent_switches_old_requests_and_preserved_history(
    feedback_client, monkeypatch, assistant, feedback
):
    client, app, _, _ = feedback_client
    calls = []
    monkeypatch.setattr(
        router,
        "query_assistant",
        lambda **kwargs: (
            calls.append(1) or QueryResponse(intent="knowledge", answer="test evidence"),
            None,
        ),
    )
    changed = client.post(
        "/api/config/backend-settings",
        json={"features": {"assistant_enabled": assistant, "feedback_enabled": feedback}},
        headers={"Authorization": "Bearer feedback-admin"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["features"]["assistant_enabled"] == assistant
    assert changed.json()["features"]["feedback_enabled"] == feedback
    assert client.get("/api/support/capabilities").json() == {
        "assistant_enabled": assistant,
        "feedback_enabled": feedback,
    }
    response = client.post(
        "/api/assistant/query", json={"message": "question", "mode": "knowledge"}
    )
    assert response.status_code == (200 if assistant else 404)
    assert len(calls) == int(assistant)
    original = "原文 preserved"
    submitted = client.post(
        "/api/feedback", json={"client_request_id": str(uuid4()), "content": original}
    )
    assert submitted.status_code == (201 if feedback else 404)
    assert (
        client.post(
            "/api/config/backend-settings",
            json={"features": {"assistant_enabled": False, "feedback_enabled": False}},
            headers={"Authorization": "Bearer feedback-admin"},
        ).status_code
        == 200
    )
    assert client.post("/api/assistant/query", json={"message": "stale page"}).status_code == 404
    assert len(calls) == int(assistant)
    history = client.get("/api/admin/feedback", headers={"Authorization": "Bearer feedback-admin"})
    assert history.status_code == 200
    assert len(history.json()["items"]) == int(feedback)
    if feedback:
        assert history.json()["items"][0]["content"] == original
        app.state.feedback_enabled = True
        assert (
            client.get(
                "/api/admin/feedback", headers={"Authorization": "Bearer feedback-admin"}
            ).json()["items"]
            == history.json()["items"]
        )


def test_model_failure_does_not_remove_direct_feedback_path(feedback_client, monkeypatch):
    client, app, _, _ = feedback_client
    app.state.assistant_enabled = True
    monkeypatch.setattr(
        router,
        "query_assistant",
        lambda **kwargs: (
            QueryResponse(
                intent="clarify",
                answer="Provider unavailable",
                availability="error",
                error_code="PROVIDER_UNAVAILABLE",
            ),
            None,
        ),
    )
    assert (
        client.post("/api/assistant/query", json={"message": "test"}).json()["error_code"]
        == "PROVIDER_UNAVAILABLE"
    )
    assert (
        client.post(
            "/api/feedback",
            json={"client_request_id": str(uuid4()), "content": "Original direct feedback"},
        ).status_code
        == 201
    )


def test_feedback_business_import_does_not_initialize_model_modules():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import ai_actuarial.feedback.store; import ai_actuarial.feedback.inbox; assert not any(x.startswith(('ai_actuarial.assistant', 'ai_actuarial.chatbot', 'ai_actuarial.rag.embeddings', 'openai')) for x in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "first",
    [
        "import ai_actuarial.assistant.query; import ai_actuarial.assistant.router",
        "import ai_actuarial.api.app",
    ],
)
def test_assistant_and_api_public_exports_work_in_both_import_orders(first):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            first
            + "; from ai_actuarial.api import create_app, run_server; import ai_actuarial.assistant.router; import ai_actuarial.api.app as app; assert create_app is app.create_app and run_server is app.run_server",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_allowlists_default_empty_and_reject_non_list_configuration(monkeypatch):
    for key in ("ASSISTANT_ENABLED", "FEEDBACK_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    config = resolve_runtime_features({})
    assert not config["assistant_enabled"] and not config["feedback_enabled"]
    assert config["assistant_public_kb_ids"] == config["assistant_staff_kb_ids"] == []
    with pytest.raises(ValueError, match="assistant_public_kb_ids"):
        resolve_runtime_features({"features": {"assistant_public_kb_ids": "all"}})


@pytest.mark.parametrize("site_key", ["", "BAD KEY"])
def test_feedback_enable_rejects_invalid_site_key_before_write_or_activation(
    feedback_client, monkeypatch, site_key
):
    import os
    from pathlib import Path

    import yaml

    client, app, _, _ = feedback_client
    path = Path(os.environ["CONFIG_PATH"])
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["features"].update(feedback_enabled=False, feedback_site_key=site_key)
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    before = path.read_bytes()
    app.state.feedback_enabled = False
    response = client.post(
        "/api/config/backend-settings",
        json={"features": {"feedback_enabled": True}},
        headers={"Authorization": "Bearer feedback-admin"},
    )
    assert response.status_code == 400
    assert path.read_bytes() == before
    assert app.state.feedback_enabled is False
