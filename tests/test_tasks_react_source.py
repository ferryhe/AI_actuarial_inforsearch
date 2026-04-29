from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
SCHEDULED_TASKS_TSX = ROOT / "pages" / "tasks" / "ScheduledTasksSection.tsx"
SCHEDULE_FROM_TASK_TSX = ROOT / "pages" / "tasks" / "ScheduleFromTaskButton.tsx"
TASKS_TSX = ROOT / "pages" / "Tasks.tsx"
LAYOUT_TSX = ROOT / "components" / "Layout.tsx"


def test_scheduled_tasks_section_uses_native_schedule_status_contract():
    src = SCHEDULED_TASKS_TSX.read_text(encoding="utf-8")

    assert "label?: string" in src
    assert "count?: number" in src
    assert "scheduleStatus.count" in src
    assert "job.label" in src


def test_scheduled_tasks_section_surfaces_write_errors_instead_of_silently_ignoring_them():
    src = SCHEDULED_TASKS_TSX.read_text(encoding="utf-8")

    assert "ApiError" in src
    assert "errorMsg" in src
    assert 'data-testid="text-scheduled-error"' in src
    assert "setErrorMsg" in src


def test_layout_no_longer_renders_fastapi_native_mode_badge():
    src = LAYOUT_TSX.read_text(encoding="utf-8")

    assert "layout.fastapiNativeMode" not in src


def test_tasks_page_has_dedicated_scheduled_tasks_view():
    src = TASKS_TSX.read_text(encoding="utf-8")

    assert 'data-testid="tasks-view-tabs"' in src
    assert 'data-testid="tab-run-tasks"' in src
    assert 'data-testid="tab-scheduled-tasks"' in src
    assert 'taskView === "scheduled"' in src
    assert "<ScheduledTasksSection />" in src


def test_add_to_schedule_uses_current_task_payload_without_manual_params_field():
    src = SCHEDULE_FROM_TASK_TSX.read_text(encoding="utf-8")

    assert "/api/scheduled-tasks/add" in src
    assert "taskParamsFromPayload" in src
    assert "delete params.type" in src
    assert 'data-testid="button-add-to-schedule"' in src
    assert 'testId="input-schedule-task-name"' in src
    assert 'testId="input-schedule-interval"' in src
    assert "input-sched-params" not in src


def test_each_task_form_exposes_add_to_schedule_control():
    form_names = [
        "SiteConfigForm.tsx",
        "WebCrawlForm.tsx",
        "AdhocUrlForm.tsx",
        "FileImportForm.tsx",
        "WebSearchForm.tsx",
        "CatalogForm.tsx",
        "MarkdownForm.tsx",
        "ChunkForm.tsx",
    ]

    for form_name in form_names:
        src = (ROOT / "pages" / "tasks" / form_name).read_text(encoding="utf-8")
        assert "ScheduleFromTaskButton" in src, form_name
        assert "buildTask" in src or "buildCollectionTask" in src, form_name


def test_recommended_markdown_conversion_tools_are_in_frontend_defaults():
    src = (ROOT / "hooks" / "use-task-options.ts").read_text(encoding="utf-8")
    settings_src = (ROOT / "pages" / "Settings.tsx").read_text(encoding="utf-8")

    for tool in ("opendataloader", "markitdown", "mistral", "docling", "mathpix"):
        assert f'"{tool}"' in src
        assert f'name: "{tool}"' in settings_src
