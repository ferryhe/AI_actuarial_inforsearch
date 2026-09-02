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


def test_database_weekly_period_labels_are_bilingual():
    src = I18N_TS.read_text(encoding="utf-8")

    for key in (
        "db.weekly_period_context",
        "db.sort_first_seen_newest",
        "db.sort_first_seen_oldest",
        "db.first_seen",
    ):
        assert src.count(f'"{key}"') == 2
