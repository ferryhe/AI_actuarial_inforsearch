from __future__ import annotations

import hashlib
import threading
from datetime import datetime, time, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from ai_actuarial.storage import Storage
from ai_actuarial.web.app import _task_log_path


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
        )
        storage._conn.commit()
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
    legacy_app = app.state.legacy_flask_app
    serializer = legacy_app.session_interface.get_signing_serializer(legacy_app)
    assert serializer is not None
    return serializer.dumps(payload)


def _install_runtime_state(monkeypatch, app) -> None:
    import ai_actuarial.web.app as legacy_web_app

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

    monkeypatch.setattr(legacy_web_app, "_active_tasks", active_tasks, raising=True)
    monkeypatch.setattr(legacy_web_app, "_task_history", task_history, raising=True)
    monkeypatch.setattr(legacy_web_app, "_task_lock", task_lock, raising=True)
    monkeypatch.setattr(legacy_web_app, "schedule", schedule_ref, raising=True)

    app.state.active_tasks_ref = active_tasks
    app.state.task_history_ref = task_history
    app.state.task_lock = task_lock
    app.state.schedule_ref = schedule_ref

    log_path = _task_log_path("task-history-1")
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
        ],
        "local": [
            {"name": "docling", "display_name": "Docling", "types": ["ocr"]},
        ],
    }

    import ai_actuarial.llm_models as llm_models

    monkeypatch.setattr(llm_models, "get_available_models", lambda provider=None: fake_models, raising=True)


def test_fastapi_ops_read_routes_match_legacy_contract(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    client, app, _seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    _install_runtime_state(monkeypatch, app)

    legacy_client = app.state.legacy_flask_app.test_client()

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

    exact_match_endpoints = {
        "/api/config/sites",
        "/api/schedule/status",
        "/api/scheduled-tasks",
        "/api/tasks/log/task-history-1?tail=500",
        "/api/config/backend-settings",
        "/api/config/llm-providers",
        "/api/config/ai-models",
        "/api/config/search-engines",
        "/api/config/categories",
    }

    for endpoint in endpoints:
        fast = client.get(endpoint)
        legacy = legacy_client.get(endpoint)
        assert fast.status_code == 200, endpoint
        assert legacy.status_code == 200, endpoint
        if endpoint in exact_match_endpoints:
            assert fast.json() == legacy.get_json(), endpoint
            continue

        fast_tasks = fast.json()["tasks"]
        legacy_tasks = legacy.get_json()["tasks"]
        assert [task["id"] for task in fast_tasks] == [task["id"] for task in legacy_tasks], endpoint
        assert [task["status"] for task in fast_tasks] == [task["status"] for task in legacy_tasks], endpoint
        assert [task.get("current_activity") for task in fast_tasks] == [task.get("current_activity") for task in legacy_tasks], endpoint

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

    cookie_name = app.state.legacy_flask_app.config.get("SESSION_COOKIE_NAME", "session")
    session_cookie = _make_session_cookie(app, {"email_user_id": seed["operator_user_id"]})
    client.cookies.set(cookie_name, session_cookie)

    log_response = client.get("/api/tasks/log/task-history-1?tail=10")
    assert log_response.status_code == 200
    assert "Completed task" in log_response.json()["log"]
