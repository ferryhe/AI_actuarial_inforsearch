"""
pytest configuration and fixtures for ai_actuarial tests.
"""

import os

import pytest


def pytest_sessionfinish(session, exitstatus):
    del session, exitstatus
    if not os.getenv("POSTGRES_TEST_URL"):
        return
    from tests.postgres_helpers import cleanup_postgres_test_schemas

    cleanup_postgres_test_schemas()


@pytest.fixture(autouse=True)
def restore_database_test_environment(monkeypatch):
    """Keep per-test PG fixture environment changes from leaking across tests."""
    original = {key: os.environ.get(key) for key in ("DATABASE_URL", "DATA_DIR")}
    yield
    # Test helpers assign these directly for legacy callers. Undo fixture
    # monkeypatches first, then restore the environment captured before setup.
    monkeypatch.undo()
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def cleanup_function_postgres_schemas(restore_database_test_environment, monkeypatch):
    """Isolate each test's PostgreSQL schema and stop app scheduler daemons."""
    if not os.getenv("POSTGRES_TEST_URL"):
        yield
        return

    from ai_actuarial.task_runtime import NativeTaskRuntime
    from tests.postgres_helpers import (
        cleanup_postgres_test_schemas,
        postgres_test_schema_snapshot,
    )

    original_init_scheduler = NativeTaskRuntime.init_scheduler

    def init_scheduler_without_background_loop(self, *args, **kwargs):
        # API tests inspect and reconcile scheduled jobs, but do not own the
        # daemon loop. Letting it outlive the function fixture can keep using
        # a schema after this fixture drops it.
        self._scheduler_loop_started = True
        return original_init_scheduler(self, *args, **kwargs)

    monkeypatch.setattr(NativeTaskRuntime, "init_scheduler", init_scheduler_without_background_loop)
    existing_schemas = postgres_test_schema_snapshot()
    yield
    cleanup_postgres_test_schemas(preserve_schemas=existing_schemas)


@pytest.fixture
def sample_task():
    """Sample task for testing."""
    return {
        "id": "test-task-001",
        "name": "Test Task",
        "status": "pending",
        "created_at": "2026-04-19T00:00:00Z",
    }


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    return {
        "id": 1,
        "email": "test@example.com",
        "role": "guest",
        "group_name": "guest",
    }


@pytest.fixture
def guest_token():
    """Generate a deterministic mock guest token."""
    import hashlib

    token_data = "guest:test-fixture"
    return hashlib.sha256(token_data.encode()).hexdigest()


@pytest.fixture
def admin_token():
    """Generate a deterministic mock admin token."""
    import hashlib

    token_data = "admin:test-fixture"
    return hashlib.sha256(token_data.encode()).hexdigest()
