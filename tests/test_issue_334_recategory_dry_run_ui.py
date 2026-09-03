import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_ROOT = ROOT / "client" / "src"
TASKS_PAGE = CLIENT_ROOT / "pages" / "Tasks.tsx"
TASKS_DIR = CLIENT_ROOT / "pages" / "tasks"
NPM_COMMAND = "npm.cmd" if os.name == "nt" else "npm"


def test_recategory_dry_run_result_runtime_contract() -> None:
    completed = subprocess.run(
        [
            NPM_COMMAND,
            "exec",
            "--",
            "tsx",
            "client/src/pages/tasks/RecategoryDryRunResult.test.tsx",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Issue 334 recategory dry-run component assertions passed" in completed.stdout


def test_recategory_precedes_catalog_in_every_task_type_selector() -> None:
    tasks = TASKS_PAGE.read_text(encoding="utf-8")
    scheduled = (TASKS_DIR / "ScheduledTasksSection.tsx").read_text(encoding="utf-8")
    history_filter = (TASKS_DIR / "FilterBar.tsx").read_text(encoding="utf-8")
    pipeline = (TASKS_DIR / "PipelineBaton.tsx").read_text(encoding="utf-8")

    run_recategory = tasks.index('{ type: "recategory", apiType: "recategory"')
    run_catalog = tasks.index('{ type: "catalog", apiType: "catalog"')
    assert run_recategory < run_catalog

    scheduled_recategory = scheduled.index(
        '{ value: "recategory", label: t("tasks.type.recategory") }'
    )
    scheduled_catalog = scheduled.index('{ value: "catalog", label: t("tasks.type.catalog") }')
    assert scheduled_recategory < scheduled_catalog

    filter_recategory = history_filter.index('<option value="recategory">')
    filter_catalog = history_filter.index('<option value="catalog">')
    assert filter_recategory < filter_catalog
    for value, translation_key in (
        ("scheduled", "tasks.type.site_config"),
        ("quick_check", "tasks.type.web_crawl"),
        ("url", "tasks.type.adhoc_url"),
        ("file", "tasks.type.file_import"),
        ("search", "tasks.type.web_search"),
        ("recategory", "tasks.type.recategory"),
        ("catalog", "tasks.type.catalog"),
        ("markdown_conversion", "tasks.type.markdown"),
        ("chunk_generation", "tasks.type.chunk"),
        ("rag_indexing", "tasks.type.rag_index"),
    ):
        assert f'<option value="{value}">{{t("{translation_key}")}}</option>' in history_filter
    assert "recategory" not in pipeline


def test_recategory_history_metadata_and_bilingual_copy_are_wired() -> None:
    tasks = TASKS_PAGE.read_text(encoding="utf-8")
    types = (TASKS_DIR / "Tasks.types.ts").read_text(encoding="utf-8")
    i18n = (CLIENT_ROOT / "hooks" / "use-i18n.ts").read_text(encoding="utf-8")

    assert "metadata?: unknown;" in types
    assert 'import { RecategoryDryRunResult } from "./tasks/RecategoryDryRunResult";' in tasks
    assert "<RecategoryDryRunResult task={logModal.task} t={t} />" in tasks

    for key, english, chinese in (
        ("title", "Dry Run Result", "试运行结果"),
        ("needed", "Recategorization is needed", "需要执行重分类"),
        ("not_needed", "Recategorization is not needed", "无需执行重分类"),
        ("removed", "Categories to remove", "待删除分类"),
        ("added", "Categories to add", "待新增分类"),
        ("article_count", "{count} articles", "{count} 篇文章"),
        ("no_changes", "No category changes detected", "未发现分类变化"),
        (
            "unavailable",
            "Dry run completed, but result details are unavailable",
            "试运行已完成，但结果详情不可用",
        ),
    ):
        assert f'"tasks.recategory_result.{key}": "{english}"' in i18n
        assert f'"tasks.recategory_result.{key}": "{chinese}"' in i18n
