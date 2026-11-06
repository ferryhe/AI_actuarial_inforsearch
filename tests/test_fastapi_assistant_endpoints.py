from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_actuarial.api import deps
from ai_actuarial.api.deps import AuthContext
from ai_actuarial.assistant import router as assistant_router
from ai_actuarial.assistant.query import QueryResponse


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.state.assistant_enabled = True
    app.include_router(assistant_router.router, prefix="/api")
    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return (
            QueryResponse(
                intent="feedback", answer="Review first", feedback_draft=kwargs["payload"].message
            ),
            None,
        )

    monkeypatch.setattr(assistant_router, "query_assistant", run)
    with TestClient(app) as test_client:
        test_client.assistant_calls = calls
        yield test_client


def test_query_response_contract_and_current_prompt_only(client):
    response = client.post(
        "/api/assistant/query", json={"message": "original", "mode": "auto", "locale": "zh"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "intent": "feedback",
        "answer": "Review first",
        "citations": [],
        "feedback_draft": "original",
        "availability": "available",
        "error_code": None,
        "generation_attempts": 0,
        "embedding_attempts": 0,
        "routing_generation_attempts": 0,
        "answer_generation_attempts": 0,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "ok", "conversation_id": "forbidden"},
        {"message": "ok", "history": []},
        {"message": "ok", "mode": "knowledge", "kb_id": "staff"},
        {"message": "ok", "mode": "knowledge", "kb_ids": []},
        {"message": " "},
        {"message": "a\0b"},
        {"message": "x" * 4001},
        {"message": "ok", "mode": "feedback"},
        {"message": "ok", "locale": "fr"},
        {"message": 42},
    ],
)
def test_invalid_old_or_unsupported_request_stops_before_runtime(client, payload):
    assert client.post("/api/assistant/query", json=payload).status_code == 422
    assert not client.assistant_calls


def test_disabled_old_client_stops_before_runtime(client):
    client.app.state.assistant_enabled = False
    assert client.post("/api/assistant/query", json={"message": "hello"}).status_code == 404
    assert not client.assistant_calls


def test_permission_rejection_stops_before_runtime(client, monkeypatch):
    monkeypatch.setattr(
        deps, "_load_auth_context", lambda request: AuthContext({"subject": "no-ai"}, frozenset())
    )
    response = client.post(
        "/api/assistant/query", json={"message": "hello"}, headers={"X-Auth-Token": "test-no-ai"}
    )
    assert response.status_code == 403
    assert not client.assistant_calls


def test_total_deadline_bounds_response(client, monkeypatch):
    monkeypatch.setattr(assistant_router, "REQUEST_SECONDS", 0.02)

    def slow(**kwargs):
        kwargs["request"].state.assistant_attempts = 1
        time.sleep(0.06)
        return QueryResponse(intent="clarify", answer="late"), None

    monkeypatch.setattr(assistant_router, "query_assistant", slow)
    response = client.post("/api/assistant/query", json={"message": "hello"})
    assert response.json()["error_code"] == "ASSISTANT_TIMEOUT"
    assert response.json()["generation_attempts"] == 1


def test_python310_asyncio_timeout_returns_stable_response(client, monkeypatch):
    class LegacyAsyncioTimeoutError(Exception):
        pass

    async def legacy_wait_for(awaitable, timeout):
        awaitable.close()
        raise LegacyAsyncioTimeoutError()

    monkeypatch.setattr(
        assistant_router,
        "asyncio",
        SimpleNamespace(
            wait_for=legacy_wait_for,
            to_thread=assistant_router.asyncio.to_thread,
            TimeoutError=LegacyAsyncioTimeoutError,
        ),
    )
    response = client.post("/api/assistant/query", json={"message": "hello", "mode": "usage"})
    assert response.status_code == 200
    assert response.json()["intent"] == "usage"
    assert response.json()["availability"] == "error"
    assert response.json()["error_code"] == "ASSISTANT_TIMEOUT"
    assert response.json()["generation_attempts"] == 0
    assert response.json()["embedding_attempts"] == 0
    assert not client.assistant_calls
