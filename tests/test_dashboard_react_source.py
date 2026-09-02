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
        "dashboard.new_materials_count",
        "dashboard.explanation_missing",
        "dashboard.explanation_empty",
        "dashboard.explanation_unavailable",
        "dashboard.explanation_failed",
        "dashboard.snapshot_unavailable",
        "dashboard.snapshot_unavailable_desc",
        "dashboard.no_weekly_snapshot",
        "dashboard.no_weekly_snapshot_desc",
        "dashboard.files_unavailable",
        "weekly.title",
        "weekly.subtitle",
        "weekly.no_highlights",
        "weekly.no_highlights_desc",
        "weekly.load_error",
    ]
    for key in expected_keys:
        assert src.count(f'"{key}"') == 2

    assert "Ask Agent" in src
    assert "询问 Agent" in src


def test_dashboard_weekly_card_drops_backend_metadata_keys():
    src = I18N_TS.read_text(encoding="utf-8")

    banned_keys = [
        "dashboard.weekly_period_start",
        "dashboard.weekly_period_end",
        "dashboard.snapshot_generated_at",
        "dashboard.explanation_generated_at",
        "dashboard.weekly_status",
        "dashboard.status_published",
        "dashboard.weekly_file_count",
        "dashboard.weekly_explanation",
    ]
    for key in banned_keys:
        assert f'"{key}"' not in src

    # Human-facing placeholder copy replaces the technical
    # "Explanation has not been generated" wording.
    assert "Explanation has not been generated" not in src
    assert "A summary for this week is being prepared." in src
    assert "本周摘要正在生成中" in src


def test_dashboard_has_single_categories_link_in_preview_header():
    src = DASHBOARD_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    # The duplicate Start Here quick action was removed: no more
    # `href: "/categories"` (object-shorthand) nor its i18n label.
    assert 'href: "/categories"' not in src
    assert 't("dashboard.browse_categories")' not in src

    # The Categories preview header keeps exactly one /categories link.
    # Match the JSX `href=` attribute (not the object-shorthand `href:`)
    # so the assertion stays robust to extra attributes on the Link.
    assert src.count('href="/categories"') == 1

    # i18n: view_all_categories defined once in English and once in Chinese.
    assert i18n_src.count('"dashboard.view_all_categories"') == 2
    assert '"View all categories"' in i18n_src
    assert '"查看全部分类"' in i18n_src

    # Weekly Additions still relies on dashboard.view_all (kept, 2x in i18n).
    assert i18n_src.count('"dashboard.view_all"') == 2
