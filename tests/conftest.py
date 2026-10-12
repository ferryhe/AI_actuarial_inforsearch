"""
pytest configuration and fixtures for ai_actuarial tests.
"""

import os
import threading
import time

import pytest

_NATIVE_TASK_THREAD_JOIN_TIMEOUT_SECONDS = 120


def _track_native_task_threads(monkeypatch, runtime_type):
    """Track runtime-owned threads before start so teardown can join task chains."""
    threads: list[threading.Thread] = []
    threads_lock = threading.Lock()
    original_start = threading.Thread.start

    def start(thread, *args, **kwargs):
        target = getattr(thread, "_target", None)
        owner = getattr(target, "__self__", None)
        if not isinstance(owner, runtime_type):
            return original_start(thread, *args, **kwargs)

        with threads_lock:
            threads.append(thread)
        try:
            return original_start(thread, *args, **kwargs)
        except BaseException:
            with threads_lock:
                threads.remove(thread)
            raise

    monkeypatch.setattr(threading.Thread, "start", start)
    return threads, threads_lock


def _join_native_task_threads(threads, threads_lock, *, timeout):
    """Join all tracked task workers, including children spawned while joining."""
    deadline = time.monotonic() + timeout
    while True:
        with threads_lock:
            alive = [thread for thread in threads if thread.is_alive()]
        if not alive:
            return

        for thread in alive:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(remaining)

        if time.monotonic() >= deadline:
            with threads_lock:
                alive = [thread for thread in threads if thread.is_alive()]
            if alive:
                details = []
                for thread in alive:
                    target = getattr(thread, "_target", None)
                    target_name = getattr(target, "__name__", "unknown task")
                    args = getattr(thread, "_args", ())
                    if target_name == "_execute_collection_task" and len(args) >= 2:
                        details.append(f"{args[1]} task {args[0]}")
                    else:
                        details.append(f"{target_name} ({thread.name})")
                raise AssertionError(
                    "NativeTaskRuntime thread(s) did not finish before PostgreSQL "
                    f"schema cleanup after {timeout}s: {', '.join(details)}"
                )


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


def _cleanup_function_postgres_schemas(restore_database_test_environment, monkeypatch):
    """Isolate each test's schema and stop runtime workers before dropping it."""
    if not os.getenv("POSTGRES_TEST_URL"):
        yield
        return

    from ai_actuarial.task_runtime import NativeTaskRuntime
    from tests.postgres_helpers import (
        cleanup_postgres_test_schemas,
        postgres_test_schema_snapshot,
    )

    task_threads, task_threads_lock = _track_native_task_threads(monkeypatch, NativeTaskRuntime)
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
    _join_native_task_threads(
        task_threads,
        task_threads_lock,
        timeout=_NATIVE_TASK_THREAD_JOIN_TIMEOUT_SECONDS,
    )
    cleanup_postgres_test_schemas(preserve_schemas=existing_schemas)


@pytest.fixture(autouse=True)
def cleanup_function_postgres_schemas(restore_database_test_environment, monkeypatch):
    yield from _cleanup_function_postgres_schemas(
        restore_database_test_environment,
        monkeypatch,
    )


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
