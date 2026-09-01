import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "client" / "src" / "pages"
TASKS_DIR = PAGES / "tasks"
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"


def test_task_metrics_runtime_ui_contract() -> None:
    result = subprocess.run(
        [
            NPM_COMMAND,
            "exec",
            "--",
            "tsx",
            "client/src/pages/tasks/TaskMetrics.test.tsx",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "task metric UI runtime assertions passed" in result.stdout


def test_all_task_result_surfaces_use_shared_metrics_component() -> None:
    helper = (TASKS_DIR / "TaskMetrics.tsx").read_text(encoding="utf-8")
    card = (TASKS_DIR / "TaskCard.tsx").read_text(encoding="utf-8")
    table = (TASKS_DIR / "TaskTable.tsx").read_text(encoding="utf-8")
    tasks = (PAGES / "Tasks.tsx").read_text(encoding="utf-8")

    assert "getTaskMetrics" in helper
    assert "TaskMetrics" in card
    assert "TaskMetrics" in table
    assert "TaskMetrics" in tasks
    assert 't("tasks.stats.downloaded")' not in table
    assert 't("tasks.stats.downloaded")' not in tasks


def test_task_metric_aliases_and_canonical_fields_are_wired() -> None:
    helper = (TASKS_DIR / "TaskMetrics.tsx").read_text(encoding="utf-8")
    types = (TASKS_DIR / "Tasks.types.ts").read_text(encoding="utf-8")

    for alias in (
        "markdown",
        "markdown_conversion",
        "chunk",
        "chunk_generation",
        "embedding",
        "embedding_generation",
        "search",
        "url",
        "file",
        "scheduled",
        "adhoc",
        "quick_check",
        "web_crawl",
        "web_search",
        "file_import",
        "adhoc_url",
    ):
        assert f'"{alias}"' in helper

    for field in (
        "files",
        "chunk_sets",
        "chunk_count",
        "reused_existing",
        "expected_count",
        "ready_count",
        "generated",
        "reused",
        "invalid_regenerated",
        "failed",
    ):
        assert field in types

    for fallback in (
        "task.catalog_scanned ?? task.items_processed",
        "task.catalog_ok ?? task.items_downloaded",
        "task.catalog_skipped ?? task.items_skipped",
        "task.catalog_errors ?? task.errors?.length",
    ):
        assert fallback in helper

    assert "task.catalog_ok ?? task.items_downloaded ?? task.items_processed ?? 0" in helper
    assert 'const LOCAL_IMPORT_TYPES = new Set(["file", "file_import"]);' in helper
    assert "if (LOCAL_IMPORT_TYPES.has(type)) return processedMetrics(task);" in helper
    assert "task.result?.chunk_sets == null" in helper
    assert "].some((value) => value != null)" in helper
    assert "task.items_processed ?? task.items_downloaded" in helper
    assert 'metric("converted", task.items_downloaded ?? task.items_processed ?? 0)' in helper
    assert "status?: string;" in helper
    for active_status in ("running", "pending", "queued", "stopping"):
        assert f'"{active_status}"' in helper
    assert "ACTIVE_STATUSES.has(status)" in helper


def test_task_metric_labels_have_english_and_chinese_translations() -> None:
    i18n = (ROOT / "client" / "src" / "hooks" / "use-i18n.ts").read_text(encoding="utf-8")

    for key, english, chinese in (
        ("processed", "Processed", "已处理"),
        ("converted", "Converted", "已转换"),
        ("expected", "Expected", "预期"),
        ("ready", "Ready", "就绪"),
    ):
        assert f'"tasks.stats.{key}": "{english}"' in i18n
        assert f'"tasks.stats.{key}": "{chinese}"' in i18n
