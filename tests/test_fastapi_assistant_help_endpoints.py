from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_actuarial.api.routers.assistant_help import router as assistant_help_router
from ai_actuarial.api.routers.support import router as support_router


@pytest.fixture
def help_client():
    app = FastAPI()
    app.state.assistant_enabled = True
    app.state.feedback_enabled = False
    app.include_router(support_router, prefix="/api")
    app.include_router(assistant_help_router, prefix="/api")
    with TestClient(app) as client:
        yield client


def test_search_and_exact_reference_return_bounded_same_version_content(help_client):
    client = help_client
    assert client.get("/api/support/capabilities").json() == {
        "feedback_enabled": False,
        "assistant_enabled": True,
    }
    response = client.get(
        "/api/assistant/help",
        params={"q": "Database search by title filename source", "language": "en", "limit": 99},
    )
    assert response.status_code == 422
    response = client.get(
        "/api/assistant/help",
        params={"q": "Database search by title filename source", "language": "en", "limit": 3},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) <= 3
    assert all(len(item["snippet"]) <= 280 for item in results)
    reference = next(item for item in results if item["section_id"] == "browse-search")
    assert set(reference) == {
        "doc_id",
        "section_id",
        "language",
        "title",
        "source_version",
        "content_hash",
        "snippet",
    }
    assert len(reference["content_hash"]) == 64
    exact = client.get("/api/assistant/help/section", params=reference)
    assert exact.status_code == 200
    assert all(exact.json()[key] == value for key, value in reference.items() if key != "snippet")
    assert "content" in exact.json() and exact.json()["content"]
    stale = client.get(
        "/api/assistant/help/section",
        params={
            **{key: value for key, value in reference.items() if key != "content_hash"},
            "content_hash": "0" * 64,
        },
    )
    assert stale.status_code == 410
    assert stale.json()["detail"]["code"] == "HELP_REFERENCE_EXPIRED"
    assert "content" not in stale.json()


def test_exact_reference_rejects_bad_and_missing_references(help_client):
    base = {
        "doc_id": "user-guide-en",
        "section_id": "browse-search",
        "language": "en",
        "title": "AI Actuarial Info Search — User Guide",
        "source_version": "1.1.2",
        "content_hash": "0" * 64,
    }
    bad = help_client.get("/api/assistant/help/section", params={**base, "language": "fr"})
    assert bad.status_code == 422
    missing = help_client.get("/api/assistant/help/section", params={**base, "doc_id": "unknown"})
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "HELP_NOT_FOUND"
    absent = help_client.get(
        "/api/assistant/help/section",
        params={key: value for key, value in base.items() if key != "content_hash"},
    )
    assert absent.status_code == 422


def test_assistant_endpoints_reject_requests_when_disabled(help_client):
    help_client.app.state.assistant_enabled = False
    search = help_client.get("/api/assistant/help", params={"q": "search", "language": "en"})
    exact = help_client.get(
        "/api/assistant/help/section",
        params={
            "doc_id": "user-guide-en",
            "section_id": "browse-search",
            "language": "en",
            "title": "Guide",
            "source_version": "1.0",
            "content_hash": "0" * 64,
        },
    )
    assert search.status_code == exact.status_code == 404
    assert search.json()["detail"]["code"] == exact.json()["detail"]["code"] == "FEATURE_DISABLED"
