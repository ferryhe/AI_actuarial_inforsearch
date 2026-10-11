from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from ai_actuarial.api.services import collection_service, files_write, import_batches, ops_write
from ai_actuarial.cli import cmd_export
from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.task_runtime import NativeTaskRuntime, _append_task_log_for_runtime
from tests.postgres_helpers import postgres_url_for_path


def test_task_history_and_logs_follow_runtime_data_root(tmp_path: Path) -> None:
    runtime = NativeTaskRuntime.__new__(NativeTaskRuntime)
    runtime.data_root = tmp_path
    runtime._append_history_to_disk({"id": "task-1"})
    _append_task_log_for_runtime(runtime, "task-1", "INFO", "saved under configured root")

    assert (tmp_path / "job_history.jsonl").read_text(
        encoding="utf-8"
    ).strip() == '{"id": "task-1"}'
    assert (tmp_path / "task_logs" / "task-1.log").read_text(encoding="utf-8") == (
        "[INFO] saved under configured root\n"
    )


def test_api_upload_and_browse_paths_follow_configured_data_root(
    monkeypatch, tmp_path: Path
) -> None:
    config = {"paths": {"data": str(tmp_path), "download_dir": "data/files"}}
    monkeypatch.setattr(files_write, "_config_data", lambda: config)
    monkeypatch.setattr(import_batches, "load_sites_config", lambda **_kwargs: config)
    monkeypatch.setattr(collection_service, "load_sites_config", lambda **_kwargs: config)
    monkeypatch.setattr(ops_write, "_load_config_data", lambda: config)
    monkeypatch.delenv("IMPORT_BATCH_ROOT", raising=False)
    (tmp_path / "example.txt").write_text("file", encoding="utf-8")

    assert files_write._download_dir() == tmp_path / "files"
    assert import_batches.import_batch_root() == tmp_path / "import_batches"
    assert collection_service.browse_folder()["path"] == str(tmp_path)
    assert ops_write.browse_folder()["path"] == str(tmp_path)


def test_rejected_task_history_and_log_follow_configured_data_root(
    monkeypatch, tmp_path: Path
) -> None:
    config = {"paths": {"data": str(tmp_path)}}
    monkeypatch.setattr(ops_write, "_load_config_data", lambda: config)
    history: list[dict[str, object]] = []

    ops_write._record_rejected_task(
        "rejected in test",
        collection_type="scheduled",
        data={},
        bridge=SimpleNamespace(task_history_ref=history, task_lock=None),
    )

    assert (tmp_path / "job_history.jsonl").is_file()
    log_file = Path(str(history[0]["log_file"]))
    assert log_file == tmp_path / "task_logs" / f"{history[0]['id']}.log"
    assert "rejected in test" in log_file.read_text(encoding="utf-8")


def test_rag_default_uses_data_root_and_absolute_override_is_preserved(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RAG_DATA_DIR", raising=False)

    assert Path(RAGConfig().data_dir) == tmp_path / "rag"
    override = tmp_path.parent / "rag-override"
    assert Path(RAGConfig(data_dir=str(override)).data_dir) == override


def test_configured_data_root_applies_without_data_dir_environment(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "sites.yaml"
    config_path.write_text(f"paths:\n  data: {tmp_path.as_posix()}\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("RAG_DATA_DIR", raising=False)

    from ai_actuarial.shared_runtime import resolve_data_path, task_log_path

    assert resolve_data_path("data/job_history.jsonl") == tmp_path / "job_history.jsonl"
    assert task_log_path("task-2") == tmp_path / "task_logs" / "task-2.log"
    assert Path(RAGConfig().data_dir) == tmp_path / "rag"


def test_cli_export_default_is_written_under_configured_data_root(
    monkeypatch, tmp_path: Path
) -> None:
    database_url = postgres_url_for_path(tmp_path / "db")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("DATA_DIR", raising=False)
    data_root = tmp_path / "data"
    config = {
        "database": {"type": "postgresql", "url_env": "DATABASE_URL"},
        "paths": {"data": str(data_root)},
    }
    monkeypatch.setattr("ai_actuarial.cli._load_config", lambda _path: config)

    assert cmd_export(Namespace(config=None, output="data/export.csv", format="csv")) == 0
    assert (data_root / "export.csv").is_file()
