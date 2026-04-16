from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.storage import Storage

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _write_config_files(base_dir: Path) -> tuple[Path, Path, Path, Path]:
    files_dir = base_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    db_path = base_dir / "index.db"
    config_path = base_dir / "sites.yaml"
    categories_path = base_dir / "categories.yaml"

    config = {
        "paths": {
            "db": str(db_path),
            "download_dir": str(files_dir),
            "updates_dir": str(base_dir / "updates"),
            "last_run_new": str(base_dir / "last_run_new.json"),
        },
        "defaults": {
            "user_agent": "test-agent/1.0",
            "max_pages": 10,
            "max_depth": 1,
            "file_exts": [".pdf", ".docx"],
        },
        "sites": [],
        "scheduled_tasks": [],
    }
    categories = {"categories": {"AI": ["artificial intelligence"], "Risk": ["capital"]}}
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    categories_path.write_text(yaml.safe_dump(categories, sort_keys=False), encoding="utf-8")
    return db_path, config_path, categories_path, files_dir



def _seed_storage(db_path: Path, files_dir: Path) -> dict[str, str]:
    alpha_path = files_dir / "alpha.pdf"
    alpha_path.write_bytes(PDF_BYTES)
    beta_path = files_dir / "beta.pdf"
    beta_path.write_bytes(PDF_BYTES + b"\n% beta")

    storage = Storage(str(db_path))
    try:
        alpha_url = "https://alpha.example/doc-a.pdf"
        beta_url = "https://beta.example/doc-b.pdf"
        alpha_sha = hashlib.sha256(alpha_path.read_bytes()).hexdigest()
        beta_sha = hashlib.sha256(beta_path.read_bytes()).hexdigest()

        storage.insert_file(
            url=alpha_url,
            sha256=alpha_sha,
            title="Alpha Document",
            source_site="alpha.example",
            source_page_url="https://alpha.example",
            original_filename="doc-a.pdf",
            local_path=str(alpha_path),
            bytes=alpha_path.stat().st_size,
            content_type="application/pdf",
        )
        storage.insert_file(
            url=beta_url,
            sha256=beta_sha,
            title="Beta Document",
            source_site="beta.example",
            source_page_url="https://beta.example",
            original_filename="doc-b.pdf",
            local_path=str(beta_path),
            bytes=beta_path.stat().st_size,
            content_type="application/pdf",
        )

        storage.upsert_catalog_item(
            item={
                "url": alpha_url,
                "sha256": alpha_sha,
                "keywords": ["ai", "solvency"],
                "summary": "Alpha summary",
                "category": "AI",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.upsert_catalog_item(
            item={
                "url": beta_url,
                "sha256": beta_sha,
                "keywords": ["risk"],
                "summary": "Beta summary",
                "category": "Risk",
            },
            pipeline_version="v1",
            status="ok",
        )
        storage.update_file_markdown(alpha_url, "# Alpha\n\nAlpha markdown.", "manual")
        storage.update_file_markdown(beta_url, "# Beta\n\nBeta markdown.", "manual")
    finally:
        storage.close()

    return {"alpha_url": alpha_url, "beta_url": beta_url}



def _seed_knowledge_bases(client: TestClient) -> None:
    for kb_id, name in [("chat-kb-a", "Chat KB A"), ("chat-kb-b", "Chat KB B")]:
        response = client.post(
            "/api/rag/knowledge-bases",
            json={
                "kb_id": kb_id,
                "name": name,
                "description": f"{name} description",
                "kb_mode": "manual",
                "chunk_size": 300,
                "chunk_overlap": 50,
            },
        )
        assert response.status_code == 201, response.text



def _build_test_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, object, dict[str, str]]:
    db_path, config_path, categories_path, files_dir = _write_config_files(tmp_path)
    seed = _seed_storage(db_path, files_dir)
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-chat-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    app = create_app()
    client = TestClient(app)
    _seed_knowledge_bases(client)
    return client, app, seed



def test_fastapi_chat_routes_are_listed_in_native_inventory(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    migration = client.get("/api/migration/status")
    body = migration.json()

    assert "/api/chat/conversations" in body["native_paths"]
    assert "/api/chat/conversations/{conversation_id}" in body["native_paths"]
    assert "/api/chat/query" in body["native_paths"]
    assert "/api/chat/knowledge-bases" in body["native_paths"]
    assert "/api/chat/available-documents" in body["native_paths"]



def test_fastapi_chat_conversation_and_catalog_surfaces_work(tmp_path: Path, monkeypatch) -> None:
    client, _app, seed = _build_test_client(tmp_path, monkeypatch)

    create = client.post("/api/chat/conversations", json={"mode": "expert"})
    assert create.status_code == 201, create.text
    conversation_id = create.json()["data"]["conversation_id"]

    listed = client.get("/api/chat/conversations")
    assert listed.status_code == 200, listed.text
    conversations = listed.json()["data"]["conversations"]
    assert any(item["conversation_id"] == conversation_id for item in conversations)

    detail = client.get(f"/api/chat/conversations/{conversation_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["conversation"]["conversation_id"] == conversation_id
    assert detail.json()["data"]["messages"] == []

    kbs = client.get("/api/chat/knowledge-bases")
    assert kbs.status_code == 200, kbs.text
    kb_ids = {item["kb_id"] for item in kbs.json()["data"]["knowledge_bases"]}
    assert {"chat-kb-a", "chat-kb-b"}.issubset(kb_ids)

    documents = client.get("/api/chat/available-documents?keywords=solvency")
    assert documents.status_code == 200, documents.text
    docs = documents.json()["data"]["documents"]
    assert len(docs) == 1
    assert docs[0]["file_url"] == seed["alpha_url"]

    deleted = client.delete(f"/api/chat/conversations/{conversation_id}")
    assert deleted.status_code == 200, deleted.text

    missing = client.get(f"/api/chat/conversations/{conversation_id}")
    assert missing.status_code == 404, missing.text



def test_fastapi_chat_query_flow_works_with_native_service_contract(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    import ai_actuarial.api.services.chat as chat_service

    class FakeConversationManager:
        def __init__(self, storage, config):
            self.storage = storage
            self.config = config
            chat_service._ensure_conversation_schema(storage)

        def create_conversation(self, user_id: str, kb_id: str | None = None, mode: str = "expert", metadata=None):
            conversation_id = "conv_test_query"
            now = "2026-04-16T00:00:00+00:00"
            self.storage._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            self.storage._conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
            self.storage._conn.execute(
                """
                INSERT INTO conversations
                (conversation_id, user_id, title, kb_id, mode, created_at, updated_at, message_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    user_id,
                    "Test Query Conversation",
                    kb_id,
                    mode,
                    now,
                    now,
                    0,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            self.storage._conn.commit()
            return conversation_id

        def get_conversation(self, conversation_id: str):
            row = self.storage._conn.execute(
                "SELECT conversation_id, user_id, title, kb_id, mode, created_at, updated_at, message_count, metadata FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "conversation_id": row[0],
                "user_id": row[1],
                "title": row[2],
                "kb_id": row[3],
                "mode": row[4],
                "created_at": row[5],
                "updated_at": row[6],
                "message_count": row[7],
                "metadata": json.loads(row[8]) if row[8] else None,
            }

        def add_message(self, conversation_id: str, role: str, content: str, citations=None, metadata=None):
            message_id = f"msg_{role}"
            self.storage._conn.execute(
                """
                INSERT OR REPLACE INTO messages
                (message_id, conversation_id, role, content, citations, created_at, token_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    json.dumps(citations) if citations else None,
                    "2026-04-16T00:00:00+00:00",
                    None,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            self.storage._conn.execute(
                "UPDATE conversations SET message_count = message_count + 1, updated_at = ? WHERE conversation_id = ?",
                ("2026-04-16T00:00:00+00:00", conversation_id),
            )
            self.storage._conn.commit()
            return message_id

        def get_context(self, conversation_id: str):
            return [{"role": "user", "content": "previous question"}]

    class FakeRetriever:
        def __init__(self, storage, config):
            self.storage = storage
            self.config = config

        def retrieve(self, query, kb_ids):
            return [
                {
                    "content": "Solvency II is an EU insurance regulatory framework.",
                    "metadata": {
                        "filename": "solvency.pdf",
                        "kb_id": "chat-kb-a",
                        "kb_name": "Chat KB A",
                        "similarity_score": 0.92,
                        "chunk_id": "chunk-1",
                        "file_url": "https://alpha.example/doc-a.pdf",
                    },
                }
            ]

    class FakeLLMClient:
        def __init__(self, config, storage=None):
            self.config = config

        def generate_response(self, query, chunks, mode, conversation_history):
            return "Solvency II is a comprehensive prudential regime for insurers."

    class FakeQueryRouter:
        def __init__(self, storage, config):
            self.storage = storage
            self.config = config

        def select_kb(self, query):
            return ["chat-kb-a"]

    class FakeConfigModule:
        class ChatbotConfig:
            @staticmethod
            def from_config(storage=None, default_mode="expert"):
                return SimpleNamespace(
                    available_modes=["expert", "summary", "tutorial", "comparison"],
                    similarity_threshold=0.35,
                    model="fake-chat-model",
                    default_mode=default_mode,
                )

    class FakeConversationModule:
        ConversationManager = FakeConversationManager

    class FakeRetrievalModule:
        RAGRetriever = FakeRetriever

    class FakeLLMModule:
        LLMClient = FakeLLMClient

    class FakeRouterModule:
        QueryRouter = FakeQueryRouter

    class FakeExceptionsModule:
        class NoResultsException(Exception):
            pass

        class EmbeddingConfigurationMismatchException(Exception):
            def __init__(self, *args, **kwargs):
                super().__init__(*args)

    monkeypatch.setattr(
        chat_service,
        "_full_chat_modules",
        lambda: {
            "config": FakeConfigModule,
            "conversation": FakeConversationModule,
            "exceptions": FakeExceptionsModule,
            "retrieval": FakeRetrievalModule,
            "llm": FakeLLMModule,
            "router": FakeRouterModule,
        },
    )

    response = client.post(
        "/api/chat/query",
        json={
            "message": "What is Solvency II?",
            "kb_ids": ["chat-kb-a"],
            "mode": "expert",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["conversation_id"] == "conv_test_query"
    assert payload["message_id"] == "msg_assistant"
    assert "Solvency II" in payload["response"]
    assert payload["metadata"]["model"] == "fake-chat-model"
    assert payload["citations"][0]["filename"] == "solvency.pdf"



def test_fastapi_chat_query_maps_llm_exceptions_to_api_error(tmp_path: Path, monkeypatch) -> None:
    client, _app, _seed = _build_test_client(tmp_path, monkeypatch)

    import ai_actuarial.api.services.chat as chat_service

    class FakeConversationManager:
        def __init__(self, storage, config):
            self.storage = storage
            chat_service._ensure_conversation_schema(storage)

        def create_conversation(self, user_id: str, kb_id: str | None = None, mode: str = "expert", metadata=None):
            conversation_id = "conv_llm_error"
            now = "2026-04-16T00:00:00+00:00"
            self.storage._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            self.storage._conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
            self.storage._conn.execute(
                "INSERT INTO conversations (conversation_id, user_id, title, kb_id, mode, created_at, updated_at, message_count, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (conversation_id, user_id, "LLM Error", kb_id, mode, now, now, 0, json.dumps(metadata) if metadata else None),
            )
            self.storage._conn.commit()
            return conversation_id

        def get_conversation(self, conversation_id: str):
            return {"conversation_id": conversation_id, "user_id": "guest:test", "title": "LLM Error", "kb_id": None, "mode": "expert", "created_at": "now", "updated_at": "now", "message_count": 0, "metadata": None}

        def add_message(self, conversation_id: str, role: str, content: str, citations=None, metadata=None):
            return f"msg_{role}"

        def get_context(self, conversation_id: str):
            return []

    class FakeRetriever:
        def __init__(self, storage, config):
            pass

        def retrieve(self, query, kb_ids):
            return [{"content": "chunk", "metadata": {"filename": "a.pdf", "kb_id": "chat-kb-a", "kb_name": "Chat KB A", "similarity_score": 0.9, "chunk_id": "chunk-1", "file_url": "https://alpha.example/doc-a.pdf"}}]

    class FakeLLMException(Exception):
        pass

    class FakeLLMClient:
        def __init__(self, config, storage=None):
            pass

        def generate_response(self, query, chunks, mode, conversation_history):
            raise FakeLLMException("provider down")

    class FakeConfigModule:
        class ChatbotConfig:
            @staticmethod
            def from_config(storage=None, default_mode="expert"):
                return SimpleNamespace(available_modes=["expert", "summary", "tutorial", "comparison"], similarity_threshold=0.35, model="fake-chat-model", default_mode=default_mode)

    class FakeConversationModule:
        ConversationManager = FakeConversationManager

    class FakeRetrievalModule:
        RAGRetriever = FakeRetriever

    class FakeLLMModule:
        LLMClient = FakeLLMClient

    class FakeRouterModule:
        QueryRouter = lambda *args, **kwargs: None

    class FakeConversationException(Exception):
        pass

    class FakeExceptionsModule:
        class NoResultsException(Exception):
            pass

        class EmbeddingConfigurationMismatchException(Exception):
            pass

        LLMException = FakeLLMException
        ConversationException = FakeConversationException
        RetrievalException = Exception

    monkeypatch.setattr(
        chat_service,
        "_full_chat_modules",
        lambda: {
            "config": FakeConfigModule,
            "conversation": FakeConversationModule,
            "exceptions": FakeExceptionsModule,
            "retrieval": FakeRetrievalModule,
            "llm": FakeLLMModule,
            "router": FakeRouterModule,
        },
    )
    monkeypatch.setattr(chat_service, "_resolve_chat_user", lambda request, auth: ("guest:test", None))

    response = client.post("/api/chat/query", json={"message": "What is Solvency II?", "kb_ids": ["chat-kb-a"], "mode": "expert"})
    assert response.status_code == 502, response.text
    assert response.json()["error"] == "LLM generation failed"



def test_apply_session_update_is_noop_without_legacy_flask_app() -> None:
    import ai_actuarial.api.services.chat as chat_service

    response = SimpleNamespace(cookies=[])
    def set_cookie(**kwargs):
        response.cookies.append(kwargs)
    response.set_cookie = set_cookie

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(legacy_flask_app=None)))
    chat_service.apply_session_update(response, request, chat_service.SessionUpdate({"guest_chat_user_id": "guest:test"}))
    assert response.cookies == []



def test_fastapi_chat_query_enforces_anonymous_ip_quota(tmp_path: Path, monkeypatch) -> None:
    client, app, _seed = _build_test_client(tmp_path, monkeypatch)
    app.state.require_auth = True

    import ai_actuarial.api.services.chat as chat_service

    class FakeConversationManager:
        def __init__(self, storage, config):
            self.storage = storage
            chat_service._ensure_conversation_schema(storage)

        def create_conversation(self, user_id: str, kb_id: str | None = None, mode: str = "expert", metadata=None):
            conversation_id = "conv_quota_test"
            now = "2026-04-16T00:00:00+00:00"
            self.storage._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            self.storage._conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (conversation_id,))
            self.storage._conn.execute(
                "INSERT INTO conversations (conversation_id, user_id, title, kb_id, mode, created_at, updated_at, message_count, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (conversation_id, user_id, "Quota Test", kb_id, mode, now, now, 0, json.dumps(metadata) if metadata else None),
            )
            self.storage._conn.commit()
            return conversation_id

        def get_conversation(self, conversation_id: str):
            return None

        def add_message(self, conversation_id: str, role: str, content: str, citations=None, metadata=None):
            return f"msg_{role}"

        def get_context(self, conversation_id: str):
            return []

    class FakeRetriever:
        def __init__(self, storage, config):
            pass

        def retrieve(self, query, kb_ids):
            return []

    class FakeLLMClient:
        def __init__(self, config, storage=None):
            pass

        def generate_response(self, query, chunks, mode, conversation_history):
            return "quota ok"

    class FakeConfigModule:
        class ChatbotConfig:
            @staticmethod
            def from_config(storage=None, default_mode="expert"):
                return SimpleNamespace(available_modes=["expert", "summary", "tutorial", "comparison"], similarity_threshold=0.35, model="fake-chat-model", default_mode=default_mode)

    class FakeConversationModule:
        ConversationManager = FakeConversationManager

    class FakeRetrievalModule:
        RAGRetriever = FakeRetriever

    class FakeLLMModule:
        LLMClient = FakeLLMClient

    class FakeRouterModule:
        QueryRouter = lambda *args, **kwargs: None

    class FakeExceptionsModule:
        class NoResultsException(Exception):
            pass

        class EmbeddingConfigurationMismatchException(Exception):
            pass

        LLMException = RuntimeError
        ConversationException = RuntimeError
        RetrievalException = RuntimeError

    monkeypatch.setattr(
        chat_service,
        "_full_chat_modules",
        lambda: {
            "config": FakeConfigModule,
            "conversation": FakeConversationModule,
            "exceptions": FakeExceptionsModule,
            "retrieval": FakeRetrievalModule,
            "llm": FakeLLMModule,
            "router": FakeRouterModule,
        },
    )
    monkeypatch.setattr(chat_service, "_resolve_chat_user", lambda request, auth: ("guest:test", None))

    payload = {"message": "hello", "kb_ids": ["chat-kb-a"], "mode": "expert"}
    first = client.post("/api/chat/query", json=payload)
    second = client.post("/api/chat/query", json=payload)
    third = client.post("/api/chat/query", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert third.status_code == 429, third.text
    assert "Daily AI chat limit reached (2/day)" in third.text
