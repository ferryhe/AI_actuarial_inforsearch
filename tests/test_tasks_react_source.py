from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
SCHEDULED_TASKS_TSX = ROOT / "pages" / "tasks" / "ScheduledTasksSection.tsx"


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
