"""Contract tests for the deprecated Agentic Chat compatibility shim."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from fastapi.testclient import TestClient

from ai_actuarial.api.middleware import rate_limit
from ai_actuarial.shared_auth import GROUP_PERMISSIONS
from ai_actuarial.storage import Storage
from tests.test_fastapi_chat_endpoints import _build_test_client, _write_chat_agentic_ready_data


CANONICAL_PATH = "/api/chat/query"
COMPATIBILITY_PATH = "/api/agentic-rag/chat"


def _prepare_ready_agentic_kb(client: TestClient, monkeypatch) -> None:
    import ai_actuarial.api.services.chat as chat_service

    monkeypatch.setattr(
        chat_service,
        "_synthesize_agentic_response",
        lambda **_kwargs: ("Deterministic agentic test answer", "deterministic_fallback"),
    )
    ready_dir = (
        Path(client.app.state.db_path).parent
        / "agentic_ready_data"
        / "kbs"
        / "chat-kb-a"
        / "regulation"
        / "1"
    )
    _write_chat_agentic_ready_data(ready_dir)


def _canonical_payload() -> dict[str, object]:
    return {
        "message": "How does Article 19 define required capital?",
        "kb_ids": ["chat-kb-a"],
        "rag_mode": "agentic",
    }


def _compatibility_payload() -> dict[str, object]:
    return {"query": "How does Article 19 define required capital?", "kb_id": "chat-kb-a"}


def test_compatibility_chat_uses_the_canonical_chat_command_end_to_end(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    _prepare_ready_agentic_kb(client, monkeypatch)

    canonical = client.post(CANONICAL_PATH, json=_canonical_payload())
    compatibility = client.post(COMPATIBILITY_PATH, json=_compatibility_payload())

    assert canonical.status_code == compatibility.status_code == 200
    assert compatibility.headers["Deprecation"] == "true"
    assert compatibility.headers["Link"] == '</api/chat/query>; rel="successor-version"'
    canonical_data = canonical.json()["data"]
    compatibility_data = compatibility.json()["data"]
    for data in (canonical_data, compatibility_data):
        assert data["metadata"]["kb_id"] == "chat-kb-a"
        assert data["metadata"]["rag_mode"] == "agentic"
        assert data["metadata"]["tool_trace"]
        detail = client.get(f"/api/chat/conversations/{data['conversation_id']}")
        assert detail.status_code == 200
        messages = detail.json()["data"]["messages"]
        assert [message["role"] for message in messages] == ["user", "assistant"]
        # Conversation messages are the Chat command's durable audit trail.
        assert messages[1]["metadata"]["rag_mode"] == "agentic"


def test_compatibility_chat_requires_chat_query_permission_on_both_paths(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch)
    app.state.require_auth = True
    monkeypatch.setitem(
        GROUP_PERMISSIONS, "catalog_only", frozenset({"catalog.read", "chat.view"})
    )
    storage = Storage(str(tmp_path / "index.db"))
    try:
        token = secrets.token_urlsafe(32)
        storage.upsert_auth_token_by_hash(
            subject="catalog-only",
            group_name="catalog_only",
            token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
    finally:
        storage.close()
    client = TestClient(app, headers={"X-Auth-Token": token})

    assert client.post(CANONICAL_PATH, json=_canonical_payload()).status_code == 403
    assert client.post(COMPATIBILITY_PATH, json=_compatibility_payload()).status_code == 403
    for path in (CANONICAL_PATH, COMPATIBILITY_PATH):
        assert client.post(path, json={}).status_code == 403


def test_compatibility_chat_shares_daily_quota_error_with_canonical_chat(
    tmp_path: Path, monkeypatch
) -> None:
    import ai_actuarial.api.services.chat as chat_service

    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)
    _prepare_ready_agentic_kb(client, monkeypatch)
    monkeypatch.setattr(
        chat_service, "AI_CHAT_QUOTA", {**chat_service.AI_CHAT_QUOTA, "operator": 1}
    )

    canonical = client.post(CANONICAL_PATH, json=_canonical_payload())
    compatibility = client.post(COMPATIBILITY_PATH, json=_compatibility_payload())

    assert canonical.status_code == 200
    assert compatibility.status_code == 429
    assert compatibility.json() == {
        "success": False,
        "error": "Daily AI chat limit reached (1/day). Daily quota exceeded.",
    }


def test_compatibility_chat_shares_per_minute_rate_limit_with_canonical_chat(
    tmp_path: Path, monkeypatch
) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch)
    _prepare_ready_agentic_kb(client, monkeypatch)
    app.state.enable_rate_limiting = True
    rate_limit._rate_limit_stores.clear()
    monkeypatch.setitem(rate_limit.ROLE_RATE_LIMITS, "operator", 1)

    canonical = client.post(CANONICAL_PATH, json=_canonical_payload())
    compatibility = client.post(COMPATIBILITY_PATH, json=_compatibility_payload())

    assert canonical.status_code == 200
    assert compatibility.status_code == 429
    canonical_limited = client.post(CANONICAL_PATH, json=_canonical_payload())
    assert canonical_limited.status_code == 429
    for response in (compatibility, canonical_limited):
        assert response.json()["detail"] == "Rate limit exceeded. Limit: 1 requests/minute."
        assert 1 <= response.json()["retry_after"] <= 60
        assert response.headers["Retry-After"] == str(response.json()["retry_after"])
        assert set(response.json()) == {"detail", "retry_after"}


def test_compatibility_chat_rejects_retired_output_dir_escape_hatch(
    tmp_path: Path, monkeypatch
) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    response = client.post(
        COMPATIBILITY_PATH,
        json={"query": "capital", "output_dir": str(tmp_path / "agentic_ready_data")},
    )

    assert response.status_code == 400
    assert response.json()["error"].startswith("output_dir is not supported")


def test_product_callers_do_not_use_the_deprecated_agentic_chat_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    caller_roots = (repo_root / "client", repo_root / "scripts", repo_root / "ai_actuarial" / "cli")
    offenders = []
    for root in caller_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".js", ".mjs", ".sh"}:
                if COMPATIBILITY_PATH in path.read_text(encoding="utf-8"):
                    offenders.append(path.relative_to(repo_root).as_posix())
    assert offenders == [], f"deprecated Agentic Chat callers: {offenders}"
