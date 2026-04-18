from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from itsdangerous import URLSafeSerializer

from ai_actuarial.api.app import create_app
from ai_actuarial.services.token_encryption import TokenEncryption
from ai_actuarial.storage import Storage


def _task_log_path(base_dir: Path, task_id: str) -> Path:
    safe_id = "".join(ch if ch.isalnum() or ch in "_.-" else "_" for ch in (task_id or "unknown"))
    return base_dir / "data" / "task_logs" / f"{safe_id}.log"


def _write_config_files(base_dir: Path) -> tuple[Path, Path, Path]:
    db_path = base_dir / "index.db"
    config_path = base_dir / "sites.yaml"
    categories_path = base_dir / "categories.yaml"

    config = {
        "paths": {
            "db": str(db_path),
            "download_dir": str(base_dir / "files"),
            "updates_dir": str(base_dir / "updates"),
            "last_run_new": str(base_dir / "last_run_new.json"),
        },
        "defaults": {
            "user_agent": "test-agent/1.0",
            "max_pages": 10,
            "max_depth": 1,
            "delay_seconds": 0.25,
            "file_exts": [".pdf", ".docx"],
            "keywords": ["ai"],
            "exclude_keywords": ["draft"],
            "exclude_prefixes": ["/private"],
            "schedule_interval": "daily",
        },
        "search": {
            "enabled": True,
            "max_results": 7,
            "delay_seconds": 0.5,
            "languages": ["en", "zh"],
            "country": "us",
            "exclude_keywords": ["jobs"],
            "queries": ["actuarial ai"],
        },
        "system": {
            "file_deletion_enabled": True,
        },
        "ai_config": {
            "catalog": {"provider": "openai", "model": "gpt-4o-mini", "system_prompt": "catalog prompt"},
            "embeddings": {"provider": "openai", "model": "text-embedding-3-large"},
            "chatbot": {
                "provider": "openai",
                "model": "gpt-4o",
                "prompts": {
                    "base": "base prompt",
                    "expert": "expert prompt",
                    "summary": "summary prompt",
                    "tutorial": "tutorial prompt",
                    "comparison": "comparison prompt",
                },
                "summarization_prompt": "summarize prompt",
            },
            "ocr": {"provider": "local", "model": "docling"},
        },
        "sites": [
            {
                "name": "Alpha Site",
                "url": "https://alpha.example",
                "max_pages": 20,
                "max_depth": 2,
                "keywords": ["pricing", "ai"],
                "exclude_keywords": ["archive"],
                "exclude_prefixes": ["/skip"],
                "schedule_interval": "weekly",
                "content_selector": "main article",
            }
        ],
        "scheduled_tasks": [
            {
                "name": "Nightly Catalog",
                "type": "catalog",
                "interval": "daily",
                "enabled": True,
                "params": {"category": "AI"},
            }
        ],
    }
    categories = {
        "categories": {
            "AI": ["artificial intelligence"],
            "Pricing": ["premium"],
        },
        "ai_filter_keywords": ["machine learning"],
        "ai_keywords": ["llm", "ai"],
    }

    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    categories_path.write_text(yaml.safe_dump(categories, sort_keys=False), encoding="utf-8")
    return db_path, config_path, categories_path


def _seed_storage(db_path: Path) -> dict[str, object]:
    storage = Storage(str(db_path))
    try:
        storage.insert_file(
            url="https://alpha.example/doc-a.pdf",
            sha256="hash-alpha",
            title="Alpha Document",
            source_site="alpha.example",
            source_page_url="https://alpha.example",
            original_filename="doc-a.pdf",
            local_path="/tmp/doc-a.pdf",
            bytes=1024,
            content_type="application/pdf",
        )
        storage.upsert_catalog_item(
            item={
                "url": "https://alpha.example/doc-a.pdf",
                "sha256": "hash-alpha",
                "keywords": ["ai"],
                "summary": "Alpha summary",
                "category": "AI; Risk",
            },
            pipeline_version="v1",
            status="ok",
        )

        reader_user_id = storage.create_user(
            "reader@example.com",
            "reader-password-hash",
            role="reader",
            display_name="Reader",
        )
        operator_user_id = storage.create_user(
            "operator@example.com",
            "operator-password-hash",
            role="operator",
            display_name="Operator",
        )

        reader_token = "reader-token"
        storage.upsert_auth_token_by_hash(
            subject="reader-token",
            group_name="reader",
            token_hash=hashlib.sha256(reader_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        operator_token = "operator-token"
        storage.upsert_auth_token_by_hash(
            subject="operator-token",
            group_name="operator",
            token_hash=hashlib.sha256(operator_token.encode("utf-8")).hexdigest(),
            is_active=True,
        )
        storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted="not-a-real-key",
            base_url="https://api.openai.example/v1",
            notes="test provider",
            category="llm",
            instance_id="primary",
            label="OpenAI Primary",
            is_default=True,
        )
        storage.upsert_llm_provider(
            provider="openai",
            api_key_encrypted="not-a-real-backup-key",
            base_url="https://backup.openai.example/v1",
            notes="backup provider",
            category="llm",
            instance_id="backup",
            label="OpenAI Backup",
            is_default=False,
        )
        storage.upsert_llm_provider(
            provider="serper",
            api_key_encrypted="not-a-real-search-key",
            base_url="https://google.serper.dev",
            notes="test search provider",
            category="search",
        )
    finally:
        storage.close()

    return {
        "reader_user_id": reader_user_id,
        "reader_token": reader_token,
        "operator_user_id": operator_user_id,
        "operator_token": operator_token,
    }


def _build_test_client(tmp_path: Path, monkeypatch, *, require_auth: bool) -> tuple[TestClient, object, dict[str, object]]:
    db_path, config_path, categories_path = _write_config_files(tmp_path)
    seed = _seed_storage(db_path)

    monkeypatch.chdir(tmp_path)
    TokenEncryption._instance = None
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("CATEGORIES_CONFIG_PATH", str(categories_path))
    monkeypatch.setenv("FLASK_SECRET_KEY", "fastapi-ops-read-test-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    if require_auth:
        monkeypatch.setenv("REQUIRE_AUTH", "true")
    else:
        monkeypatch.delenv("REQUIRE_AUTH", raising=False)

    app = create_app()
    client = TestClient(app)
    return client, app, seed


def _make_session_cookie(app, payload: dict[str, object]) -> str:
    serializer = URLSafeSerializer(app.state.fastapi_session_secret, salt="fastapi-session")
    return serializer.dumps(payload)


def _install_runtime_state(monkeypatch, app) -> None:
    active_tasks = {
        "task-live": {
            "id": "task-live",
            "name": "Live Crawl",
            "type": "scheduled",
            "status": "running",
            "progress": 35,
            "started_at": "2026-04-15T07:00:00+00:00",
            "current_activity": "Fetching https://alpha.example",
            "items_processed": 7,
            "items_total": 20,
            "items_downloaded": 3,
            "items_skipped": 1,
            "errors": [],
        }
    }
    task_history = [
        {
            "id": "task-history-1",
            "name": "Nightly Catalog",
            "type": "catalog",
            "status": "completed",
            "started_at": "2026-04-15T05:00:00+00:00",
            "completed_at": "2026-04-15T05:20:00+00:00",
            "items_processed": 12,
            "items_downloaded": 12,
            "items_skipped": 0,
            "errors": [],
            "catalog_ok": 12,
        },
        {
            "id": "task-history-2",
            "name": "Older Run",
            "type": "scheduled",
            "status": "failed",
            "started_at": "2026-04-14T05:00:00+00:00",
            "completed_at": "2026-04-14T05:01:00+00:00",
            "items_processed": 2,
            "items_downloaded": 0,
            "items_skipped": 0,
            "errors": ["boom"],
        },
    ]
    task_lock = threading.Lock()

    class DummyJob:
        def __init__(self):
            self.next_run = datetime(2026, 4, 16, 6, 0, tzinfo=timezone.utc)
            self.last_run = datetime(2026, 4, 15, 6, 0, tzinfo=timezone.utc)
            self.unit = "days"
            self.interval = 1
            self.at_time = time(6, 0)
            self.start_day = "monday"

    schedule_ref = SimpleNamespace(jobs=[DummyJob()])

    app.state.active_tasks_ref = active_tasks
    app.state.task_history_ref = task_history
    app.state.task_lock = task_lock
    app.state.schedule_ref = schedule_ref

    log_path = _task_log_path(Path.cwd(), "task-history-1")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        "2026-04-15 05:00:00 INFO Started task\n2026-04-15 05:20:00 INFO Completed task\n",
        encoding="utf-8",
    )


def _patch_available_models(monkeypatch) -> None:
    fake_models = {
        "openai": [
            {"name": "gpt-4o-mini", "display_name": "GPT-4o Mini", "types": ["catalog", "chatbot"]},
            {"name": "text-embedding-3-large", "display_name": "Text Embedding 3 Large", "types": ["embeddings"]},
            {"name": "text-embedding-3-small", "display_name": "Text Embedding 3 Small", "types": ["embeddings"]},
        ],
        "mistral": [
            {"name": "mistral-small-latest", "display_name": "Mistral Small Latest", "types": ["catalog", "chatbot"]},
        ],
        "local": [
            {"name": "docling", "display_name": "Docling", "types": ["ocr"]},
        ],
    }

    import ai_actuarial.llm_models as llm_models

    monkeypatch.setattr(llm_models, "get_available_models", lambda provider=None: fake_models, raising=True)


def test_fastapi_ops_read_routes_are_native_and_return_expected_shapes(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    _install_runtime_state(monkeypatch, app)

    endpoints = [
        "/api/config/sites",
        "/api/schedule/status",
        "/api/scheduled-tasks",
        "/api/tasks/active",
        "/api/tasks/history?limit=20",
        "/api/tasks/log/task-history-1?tail=500",
        "/api/config/backend-settings",
        "/api/config/llm-providers",
        "/api/config/ai-models",
        "/api/config/search-engines",
        "/api/config/categories",
    ]

    for endpoint in endpoints:
        fast = client.get(endpoint)
        assert fast.status_code == 200, endpoint
        body = fast.json()
        if endpoint == "/api/config/sites":
            assert body["sites"][0]["name"] == "Alpha Site"
        elif endpoint == "/api/schedule/status":
            assert body["count"] == 1
            assert body["jobs"][0]["label"].startswith("daily")
        elif endpoint == "/api/scheduled-tasks":
            assert body["tasks"][0]["name"] == "Nightly Catalog"
        elif endpoint == "/api/tasks/active":
            assert body["tasks"][0]["id"] == "task-live"
        elif endpoint == "/api/tasks/history?limit=20":
            assert body["tasks"][0]["id"] == "task-history-1"
        elif endpoint == "/api/tasks/log/task-history-1?tail=500":
            assert "Completed task" in body["log"]
        elif endpoint == "/api/config/backend-settings":
            assert body["defaults"]["max_pages"] == 10
        elif endpoint == "/api/config/llm-providers":
            assert any(item["provider"] == "openai" for item in body["providers"])
        elif endpoint == "/api/config/ai-models":
            assert "openai" in body["available"]
        elif endpoint == "/api/config/search-engines":
            assert any(item["id"] == "brave" for item in body["engines"])
        elif endpoint == "/api/config/categories":
            assert "AI" in body["categories"]

    migration = client.get("/api/migration/status")
    body = migration.json()
    assert "/api/config/sites" in body["native_paths"]
    assert "/api/tasks/active" in body["native_paths"]
    assert "/api/config/backend-settings" in body["native_paths"]


def test_fastapi_ops_read_routes_require_operator_access_when_auth_enabled(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    _install_runtime_state(monkeypatch, app)

    unauthorized = client.get("/api/config/sites")
    assert unauthorized.status_code == 401

    forbidden = client.get(
        "/api/config/sites",
        headers={"Authorization": f"Bearer {seed['reader_token']}"},
    )
    assert forbidden.status_code == 403

    authorized = client.get(
        "/api/config/sites",
        headers={"Authorization": f"Bearer {seed['operator_token']}"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["sites"][0]["name"] == "Alpha Site"

    cookie_name = app.state.fastapi_session_cookie_name
    session_cookie = _make_session_cookie(app, {"email_user_id": seed["operator_user_id"]})
    client.cookies.set(cookie_name, session_cookie)

    log_response = client.get("/api/tasks/log/task-history-1?tail=10")
    assert log_response.status_code == 200
    assert "Completed task" in log_response.json()["log"]


def test_fastapi_ai_config_registry_credentials_and_routing_read_endpoints(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    _install_runtime_state(monkeypatch, app)

    providers = client.get("/api/config/providers")
    assert providers.status_code == 200, providers.text
    provider_rows = providers.json()["providers"]
    provider_ids = {row["provider_id"] for row in provider_rows}
    assert any(row["provider_id"] == "openai" for row in provider_rows)
    assert {"azure_openai", "openrouter", "vllm", "localai", "huggingface", "volcengine", "tencent_cloud", "baiduyiyan", "xunfei_spark", "google_cloud", "bedrock", "fish_audio", "mineru", "paddleocr"}.issubset(provider_ids)
    openai_row = next(row for row in provider_rows if row["provider_id"] == "openai")
    assert openai_row["supports"]["chat"] is True
    assert openai_row["supports"]["embeddings"] is True

    credentials = client.get("/api/config/provider-credentials")
    assert credentials.status_code == 200, credentials.text
    credential_rows = credentials.json()["credentials"]
    openai_credentials = [row for row in credential_rows if row["provider_id"] == "openai" and row["source"] == "db"]
    assert len(openai_credentials) == 2
    assert any(row["instance_id"] == "primary" and row["is_default"] is True for row in openai_credentials)
    assert any(row["instance_id"] == "backup" and row["is_default"] is False for row in openai_credentials)
    assert any(row["provider_id"] == "serper" and row["category"] == "search" for row in credential_rows)

    catalog = client.get("/api/config/model-catalog")
    assert catalog.status_code == 200, catalog.text
    catalog_body = catalog.json()
    assert "openai" in catalog_body["available"]

    routing = client.get("/api/config/ai-routing")
    assert routing.status_code == 200, routing.text
    bindings = {item["function_name"]: item for item in routing.json()["bindings"]}
    assert bindings["chat"]["config_section"] == "chatbot"
    assert bindings["embeddings"]["provider"] == "openai"
    assert bindings["embeddings"]["credential_id"]
    assert bindings["embeddings"]["configured"] is True
    assert bindings["embeddings"]["embedding_dimension"] == 3072
    assert bindings["embeddings"]["embedding_fingerprint"].startswith("openai:text-embedding-3-large:")

def test_fastapi_global_logs_read_endpoint_is_native(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENABLE_GLOBAL_LOGS_API", "1")
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "app.log").write_text(
        "2026-04-17 10:00:00 INFO first\n2026-04-17 10:01:00 ERROR second\n",
        encoding="utf-8",
    )

    storage = Storage(str(app.state.db_path))
    try:
        admin_user_id = storage.create_user(
            "admin@example.com",
            "admin-password-hash",
            role="admin",
            display_name="Admin",
        )
    finally:
        storage.close()

    cookie_name = app.state.fastapi_session_cookie_name
    session_cookie = _make_session_cookie(app, {"email_user_id": admin_user_id})
    client.cookies.set(cookie_name, session_cookie)

    response = client.get("/api/logs/global")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["logs"].splitlines()[0].endswith("ERROR second")
    assert body["logs"].splitlines()[1].endswith("INFO first")
