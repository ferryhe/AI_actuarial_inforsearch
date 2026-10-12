from __future__ import annotations

import threading
import time

import psycopg2
import pytest

from ai_actuarial.task_runtime import NativeTaskRuntime
from tests import conftest, postgres_helpers


class _ChainedTaskRuntime(NativeTaskRuntime):
    def __init__(self, data_root) -> None:
        self.data_root = data_root
        self.active_tasks = {}
        self.task_history = []
        self.task_lock = threading.RLock()
        self.parent_started = threading.Event()
        self.allow_parent_to_spawn = threading.Event()
        self.parent_finished = threading.Event()
        self.child_started = threading.Event()
        self.child_finished = threading.Event()
        self.release_child = threading.Event()
        self.worker_threads: list[threading.Thread] = []
        self.worker_threads_lock = threading.Lock()

    def _execute_collection_task(self, _task_id, collection_type, _data) -> None:
        with self.worker_threads_lock:
            self.worker_threads.append(threading.current_thread())
        if collection_type == "parent":
            self.parent_started.set()
            self.allow_parent_to_spawn.wait()
            try:
                self.start_background_task("child", {})
            finally:
                self.parent_finished.set()
            return
        self.child_started.set()
        self.release_child.wait()
        self.child_finished.set()


def _begin_cleanup_fixture(monkeypatch, cleanup):
    monkeypatch.setenv("POSTGRES_TEST_URL", "postgresql://test.invalid/unused")
    monkeypatch.setattr(postgres_helpers, "cleanup_postgres_test_schemas", cleanup)
    monkeypatch.setattr(
        postgres_helpers,
        "postgres_test_schema_snapshot",
        lambda: frozenset({"preexisting"}),
    )
    fixture = conftest._cleanup_function_postgres_schemas(None, monkeypatch)
    next(fixture)
    return fixture


def _finish_workers(runtime: _ChainedTaskRuntime) -> None:
    deadline = time.monotonic() + 5
    while True:
        with runtime.worker_threads_lock:
            threads = list(runtime.worker_threads)
        alive = [thread for thread in threads if thread.is_alive()]
        if not alive:
            return
        for thread in alive:
            thread.join(timeout=max(0, deadline - time.monotonic()))
        assert time.monotonic() < deadline or all(not thread.is_alive() for thread in alive)


def test_postgres_schema_cleanup_waits_for_a_child_runtime_task(tmp_path) -> None:
    runtime = _ChainedTaskRuntime(tmp_path)
    cleanup_called = threading.Event()
    cleanup_saw_finished_child: list[bool] = []
    fixture_errors: list[BaseException] = []

    def cleanup(**_kwargs) -> None:
        cleanup_saw_finished_child.append(runtime.child_finished.is_set())
        cleanup_called.set()

    with pytest.MonkeyPatch.context() as monkeypatch:
        fixture = _begin_cleanup_fixture(monkeypatch, cleanup)
        runtime.start_background_task("parent", {})
        assert runtime.parent_started.wait(timeout=5)

        fixture_finished = threading.Event()
        join_started = threading.Event()
        original_join = conftest._join_native_task_threads

        def observe_join(*args, **kwargs):
            join_started.set()
            return original_join(*args, **kwargs)

        monkeypatch.setattr(conftest, "_join_native_task_threads", observe_join)

        def finish_fixture() -> None:
            try:
                next(fixture)
            except StopIteration:
                pass
            except BaseException as exc:  # surfaced in the test thread below
                fixture_errors.append(exc)
            finally:
                fixture_finished.set()

        teardown_thread = threading.Thread(target=finish_fixture)
        teardown_thread.start()
        try:
            assert join_started.wait(timeout=5)
            runtime.allow_parent_to_spawn.set()
            assert runtime.child_started.wait(timeout=5)
            assert runtime.parent_finished.wait(timeout=5)
            assert not fixture_finished.wait(timeout=0.1)
            assert not cleanup_called.is_set()
        finally:
            runtime.allow_parent_to_spawn.set()
            runtime.release_child.set()
            runtime.child_started.wait(timeout=5)
            teardown_thread.join(timeout=5)
            assert not teardown_thread.is_alive()
            _finish_workers(runtime)

        assert fixture_finished.wait(timeout=5)

    assert fixture_errors == []
    assert cleanup_called.is_set()
    assert cleanup_saw_finished_child == [True]


def test_postgres_schema_cleanup_timeout_fails_before_drop(tmp_path) -> None:
    runtime = _ChainedTaskRuntime(tmp_path)
    cleanup_called = False

    def cleanup(*, preserve_schemas) -> None:
        nonlocal cleanup_called
        del preserve_schemas
        cleanup_called = True

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(conftest, "_NATIVE_TASK_THREAD_JOIN_TIMEOUT_SECONDS", 0.05)
        fixture = _begin_cleanup_fixture(monkeypatch, cleanup)
        runtime.start_background_task("parent", {})

        try:
            assert runtime.parent_started.wait(timeout=5)
            runtime.allow_parent_to_spawn.set()
            assert runtime.child_started.wait(timeout=5)
            with pytest.raises(
                AssertionError,
                match="did not finish before PostgreSQL schema cleanup after 0.05s",
            ):
                next(fixture)
            assert cleanup_called is False
        finally:
            runtime.allow_parent_to_spawn.set()
            runtime.release_child.set()
            runtime.child_started.wait(timeout=5)
            _finish_workers(runtime)

        assert runtime.child_finished.is_set()


def test_schema_drop_lock_timeout_failure_preserves_schema_cache() -> None:
    commands: list[str] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql):
            commands.append(sql)
            if sql.startswith("DROP SCHEMA"):
                raise psycopg2.OperationalError("synthetic lock timeout")

    class AdminConnection:
        autocommit = False
        closed = False

        def cursor(self):
            return Cursor()

        def close(self):
            self.closed = True

    admin = AdminConnection()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("POSTGRES_TEST_URL", "postgresql://test.invalid/unused")
        monkeypatch.setattr(postgres_helpers.psycopg2, "connect", lambda _url: admin)
        monkeypatch.setattr(
            postgres_helpers,
            "quote_ident",
            lambda schema, _cursor: f'"{schema}"',
        )
        monkeypatch.setattr(postgres_helpers, "_schemas", {"test_owned"})
        monkeypatch.setattr(postgres_helpers, "_schema_urls", {"test_owned": "test-url"})
        monkeypatch.setattr(postgres_helpers, "_urls", {"test-key": "test-url"})
        monkeypatch.setattr(postgres_helpers, "_data_roots", {"test-url": "test-root"})

        with pytest.raises(
            psycopg2.OperationalError,
            match="synthetic lock timeout",
        ):
            postgres_helpers.cleanup_postgres_test_schemas()

        assert commands == [
            "SET lock_timeout = '30s'",
            'DROP SCHEMA IF EXISTS "test_owned" CASCADE',
        ]
        assert admin.closed is True
        assert postgres_helpers._schemas == {"test_owned"}
        assert postgres_helpers._schema_urls == {"test_owned": "test-url"}
        assert postgres_helpers._urls == {"test-key": "test-url"}
        assert postgres_helpers._data_roots == {"test-url": "test-root"}
