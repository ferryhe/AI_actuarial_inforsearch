from pathlib import Path


DASHBOARD_TSX = Path(__file__).resolve().parents[1] / "client" / "src" / "pages" / "Dashboard.tsx"
I18N_TS = Path(__file__).resolve().parents[1] / "client" / "src" / "hooks" / "use-i18n.ts"


def test_dashboard_uses_customer_facing_entries_not_backend_ops_statuses():
    src = DASHBOARD_TSX.read_text(encoding="utf-8")

    assert 'apiGet<CategoriesResponse>("/api/categories?mode=used")' in src
    assert "Promise.allSettled" in src
    assert "loadLatestWeeklyDashboard()" in src
    assert "WeeklyDashboardSection" in src
    assert "weekly?.snapshot?.file_count" in src
    assert "isThisCalendarWeek" not in src
    assert "buildFileDetailPath(url" in src
    assert "databaseCategoryPath(category.name)" in src
    assert 'href: "/chat"' in src

    banned_dashboard_terms = [
        "cataloged_files",
        "active_tasks",
        "task_center",
        "knowledge_bases",
        "RAG",
        "chunk",
        "embedding",
    ]
    for term in banned_dashboard_terms:
        assert term not in src


def test_dashboard_i18n_has_customer_facing_en_and_zh_labels():
    src = I18N_TS.read_text(encoding="utf-8")

    expected_keys = [
        "dashboard.materials",
        "dashboard.categories",
        "dashboard.this_week_additions",
        "dashboard.browse_materials",
        "dashboard.ask_agent",
        "dashboard.no_weekly_files",
        "dashboard.weekly_period_start",
        "dashboard.weekly_period_end",
        "dashboard.snapshot_generated_at",
        "dashboard.explanation_generated_at",
        "dashboard.weekly_status",
        "dashboard.status_published",
        "dashboard.weekly_file_count",
        "dashboard.weekly_explanation",
        "dashboard.explanation_missing",
        "dashboard.explanation_empty",
        "dashboard.explanation_unavailable",
        "dashboard.explanation_failed",
        "dashboard.snapshot_unavailable",
        "dashboard.snapshot_unavailable_desc",
        "dashboard.no_weekly_snapshot",
        "dashboard.no_weekly_snapshot_desc",
        "dashboard.files_unavailable",
    ]
    for key in expected_keys:
        assert src.count(f'"{key}"') == 2

    assert "Ask Agent" in src
    assert "询问 Agent" in src
