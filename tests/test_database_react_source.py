from pathlib import Path

DATABASE_TSX = Path(__file__).resolve().parents[1] / "client" / "src" / "pages" / "Database.tsx"
I18N_TS = Path(__file__).resolve().parents[1] / "client" / "src" / "hooks" / "use-i18n.ts"


def test_database_pagination_supports_direct_page_jump():
    src = DATABASE_TSX.read_text(encoding="utf-8")

    assert "pageJumpInput" in src
    assert "handlePageJump" in src
    assert "Number.parseInt(pageJumpInput" not in src
    assert "/^\\d+$/.test(normalizedPage)" in src
    assert "Number.isSafeInteger(parsedPage)" in src
    assert "setOffset((targetPage - 1) * PAGE_SIZE)" in src
    assert 'data-testid="input-page-jump"' in src
    assert 'data-testid="button-page-jump"' in src
    assert 'onKeyDown={(e) => e.key === "Enter" && handlePageJump()}' in src


def test_database_file_rows_offer_ai_explain_via_chat_route_state():
    src = DATABASE_TSX.read_text(encoding="utf-8")

    assert "function explainFile(file: FileItem)" in src
    assert 'navigate("/chat"' in src
    assert 'navigate<ExplainDocumentState>("/chat"' not in src
    assert "explainDocument: {" in src
    assert "file_url: file.url" in src
    assert "filename," in src
    assert "title: displayName" in src
    assert "getCanonicalDisplayName(file" in src
    assert 'category: file.category || ""' in src
    assert "data-testid={`button-ai-explain-${i}`}" in src
    assert "data-testid={`button-ai-explain-mobile-${i}`}" in src
    assert "disabled={!hasMd || isDeleted}" in src


def test_database_header_does_not_render_fastapi_native_badge():
    src = DATABASE_TSX.read_text(encoding="utf-8")

    assert "db.fastapi_file_actions" not in src


def test_database_distinguishes_load_failure_from_a_true_empty_result():
    src = DATABASE_TSX.read_text(encoding="utf-8")
    i18n = I18N_TS.read_text(encoding="utf-8")

    assert "resolveCachedListLoadState" in src
    assert "const [loadError, setLoadError] = useState(false)" in src
    assert 'data-testid="database-load-error"' in src
    assert 't("db.load_error")' in src
    assert i18n.count('"db.load_error"') == 2


def test_database_weekly_period_labels_are_bilingual():
    src = I18N_TS.read_text(encoding="utf-8")

    for key in (
        "db.weekly_period_context",
        "db.sort_first_seen_newest",
        "db.sort_first_seen_oldest",
        "db.first_seen",
        "db.keywords",
        "db.summary",
        "db.deselect_all",
        "db.select_file",
        "db.deselect_file",
    ):
        assert src.count(f'"{key}"') == 2


def test_database_desktop_rows_are_content_first_and_always_show_first_seen():
    src = DATABASE_TSX.read_text(encoding="utf-8")

    assert "keywords: unknown" in src
    assert "data-testid={`text-category-${i}`}" in src
    assert "data-testid={`text-keywords-${i}`}" in src
    assert "data-testid={`text-summary-${i}`}" in src
    assert "line-clamp-3" in src
    assert "[overflow-wrap:anywhere]" in src
    assert "const displayDate = file.first_seen" in src
    assert "data-testid={`text-md-${i}`}" not in src
    assert "data-testid={`text-size-${i}`}" not in src
    assert 't("table.md")' not in src
    assert 't("table.size")' not in src
    assert src.count("lg:hidden") >= 2


def test_database_icon_controls_stop_navigation_and_have_accessible_names():
    src = DATABASE_TSX.read_text(encoding="utf-8")

    for test_id in (
        "checkbox-select-${i}",
        "checkbox-select-mobile-${i}",
        "button-ai-explain-${i}",
        "button-preview-${i}",
        "button-download-${i}",
    ):
        marker = f"data-testid={{`{test_id}`}}"
        assert marker in src

    assert src.count("e.stopPropagation();") >= 8
    assert "aria-label={selectionLabel}" in src
    assert "title={selectionLabel}" in src
    assert "aria-label={explainLabel}" in src
    assert 'aria-label={t("db.preview")}' in src
    assert 'aria-label={t("db.download")}' in src
    assert 'aria-label={t("db.clear_search")}' in src
    assert 'title={t("db.clear_search")}' in src


def test_database_uses_category_specific_public_metadata_normalization():
    src = DATABASE_TSX.read_text(encoding="utf-8")
    i18n = I18N_TS.read_text(encoding="utf-8")

    assert "normalizePublicCategory(file.category)" in src
    assert "normalizePublicMetadataText(file.category)" not in src
    assert i18n.count('"db.clear_search"') == 2
