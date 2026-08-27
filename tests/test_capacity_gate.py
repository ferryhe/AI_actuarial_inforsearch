from __future__ import annotations

import pytest

from ai_actuarial.capacity import CapacityBlockedError, capacity_status, ensure_capacity
from ai_actuarial.task_runtime import NativeTaskRuntime


class _SentinelError(Exception):
    pass


def test_capacity_status_blocks_at_threshold() -> None:
    below = capacity_status("/", threshold_percent=80, disk_usage=(100, 79, 21))
    blocked = capacity_status("/", threshold_percent=80, disk_usage=(100, 80, 20))

    assert below["blocked"] is False
    assert blocked["blocked"] is True
    assert blocked["used_percent"] == 80.0
    assert blocked["free_bytes"] == 20


def test_capacity_status_does_not_block_below_threshold_despite_rounding() -> None:
    # 79.996% would round up to 80.0 under round(..., 2); the raw value is
    # below 80% and must NOT be blocked (regression for the round-before-compare bug).
    status = capacity_status(
        "/", threshold_percent=80, disk_usage=(100000, 79996, 20004)
    )
    assert status["blocked"] is False


def test_capacity_status_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        capacity_status("/", threshold_percent=0, disk_usage=(100, 50, 50))
    with pytest.raises(ValueError):
        capacity_status("/", threshold_percent=101, disk_usage=(100, 50, 50))


def test_capacity_status_rejects_non_positive_total() -> None:
    with pytest.raises(ValueError):
        capacity_status("/", disk_usage=(0, 0, 0))


def test_ensure_capacity_raises_when_blocked() -> None:
    with pytest.raises(CapacityBlockedError) as excinfo:
        ensure_capacity("/", operation="recategory", disk_usage=(100, 80, 20))
    message = str(excinfo.value)
    assert "[CAPACITY_BLOCKED]" in message
    assert "recategory" in message
    assert "80%" in message
    assert "at or over" in message
    assert "disk" in message
    assert "free" in message
    assert "/data" in message
    assert "object storage" in message


def test_ensure_capacity_returns_status_when_ok() -> None:
    status = ensure_capacity("/", operation="rag_indexing", disk_usage=(100, 79, 21))
    assert status["blocked"] is False


def test_run_collection_blocks_write_heavy_types_when_full(monkeypatch) -> None:
    runtime = NativeTaskRuntime()
    calls: list[str] = []

    def fake_ensure(path: str = "/", operation: str = ""):
        calls.append(operation)
        raise CapacityBlockedError(
            operation=operation,
            path=path,
            used_percent=80.0,
            threshold_percent=80.0,
            free_bytes=0,
        )

    monkeypatch.setattr("ai_actuarial.task_runtime.ensure_capacity", fake_ensure)
    monkeypatch.setattr(runtime, "_load_site_config", dict)

    for gated in ("recategory", "rag_indexing"):
        with pytest.raises(CapacityBlockedError):
            runtime._run_collection("task-id", gated, {})

    assert calls == ["recategory", "rag_indexing"]


@pytest.mark.parametrize(
    "collection_type",
    ["url", "file", "search", "scheduled", "catalog", "markdown_conversion"],
)
def test_run_collection_skips_gate_for_non_write_heavy_types(monkeypatch, collection_type) -> None:
    runtime = NativeTaskRuntime()
    calls: list[str] = []

    def fake_ensure(path: str = "/", operation: str = ""):
        calls.append(operation)
        return {"blocked": False}

    def boom(db_path: str):
        raise _SentinelError("storage reached")

    monkeypatch.setattr("ai_actuarial.task_runtime.ensure_capacity", fake_ensure)
    monkeypatch.setattr("ai_actuarial.task_runtime.Storage", boom)
    monkeypatch.setattr(runtime, "_load_site_config", dict)

    with pytest.raises(_SentinelError):
        runtime._run_collection("task-id", collection_type, {})

    assert calls == []
