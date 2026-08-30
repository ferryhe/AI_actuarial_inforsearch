from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
APP_TSX = ROOT / "App.tsx"
SECTION_TSX = ROOT / "components" / "WeeklyDashboardSection.tsx"
CARD_TSX = ROOT / "components" / "WeeklyHighlightCard.tsx"
WEEKLY_TSX = ROOT / "pages" / "Weekly.tsx"
LIB_TS = ROOT / "lib" / "weekly-dashboard.ts"


def test_weekly_card_drops_backend_metadata_fields():
    section = SECTION_TSX.read_text(encoding="utf-8")
    card = CARD_TSX.read_text(encoding="utf-8")

    # No raw timestamp / status / full-file-count metadata rendering.
    for term in [
        "view.periodStart",
        "view.periodEnd",
        "view.snapshotGeneratedAt",
        "view.explanationGeneratedAt",
        "snapshot.generated_at",
        "snapshot.period_start",
        "snapshot.period_end",
        "dashboard.weekly_status",
        "dashboard.weekly_file_count",
        "dashboard.status_published",
        "dashboard.weekly_explanation",
    ]:
        assert term not in section, term
        assert term not in card, term

    # The deterministic "N new materials" tag is driven by file_count.
    assert 't("dashboard.new_materials_count").replace("{count}", String(view.fileCount))' in card
    assert 'data-testid="weekly-new-count"' in card


def test_weekly_card_links_to_history_and_database_filter():
    section = SECTION_TSX.read_text(encoding="utf-8")

    # Top "View all" now routes to the new /weekly history page.
    assert 'href="/weekly"' in section
    # Bottom "View all" reuses the database period-filter path.
    assert "buildWeeklyDatabasePath(snapshot)" in section
    assert "<WeeklyHighlightCard" in section


def test_weekly_lib_loads_list_and_detail_without_write_ops():
    lib = LIB_TS.read_text(encoding="utf-8")

    # List endpoint for the master list (no N+1, no files/explanation).
    assert 'get<WeeklyUpdateListResponse>("/api/weekly-updates")' in lib

    # Detail fetches detail + files + explanation in parallel, read-only.
    assert "loadWeeklyUpdateDetail" in lib
    assert "Promise.allSettled" in lib
    assert 'get<WeeklySnapshotDetailEnvelope>(`/api/weekly-updates/${snapshotId}`)' in lib
    assert "/files?limit=" in lib
    assert "/explanation" in lib

    # Never triggers the generate / retry write endpoints.
    assert "explanation/generate" not in lib
    assert "explanation/retry" not in lib
    assert "apiPost" not in lib

    # The view no longer surfaces timestamp metadata fields.
    assert "periodStart:" not in lib
    assert "snapshotGeneratedAt:" not in lib
    assert "explanationGeneratedAt:" not in lib


def test_weekly_route_registered():
    app = APP_TSX.read_text(encoding="utf-8")
    assert 'import Weekly from "@/pages/Weekly"' in app
    assert 'path="/weekly"' in app
    assert "<Weekly />" in app


def test_weekly_page_master_detail_read_only():
    src = WEEKLY_TSX.read_text(encoding="utf-8")

    # Master list loaded once from the lightweight list endpoint.
    assert "loadWeeklyUpdateList()" in src
    # Detail fetched on demand for the selected item.
    assert "loadWeeklyUpdateDetail(selectedId)" in src

    # Master-detail layout with default selection of the most recent item.
    assert 'data-testid="weekly-list"' in src
    assert 'data-testid="weekly-detail"' in src
    assert "setSelectedId(items[0].id)" in src

    # Read-only: no generate / retry write operations.
    assert "generate" not in src
    assert "retry" not in src

    # Reuses the shared card and database filter path for the detail pane.
    assert "<WeeklyHighlightCard" in src
    assert "buildWeeklyDatabasePath(detail.snapshot)" in src
