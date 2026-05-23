from pathlib import Path


DATABASE_TSX = Path(__file__).resolve().parents[1] / "client" / "src" / "pages" / "Database.tsx"


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
    assert 'navigate<ExplainDocumentState>("/chat"' in src
    assert "explainDocument: {" in src
    assert "file_url: file.url" in src
    assert "filename," in src
    assert "title: file.title || filename" in src
    assert "category: file.category || \"\"" in src
    assert 'data-testid={`button-ai-explain-${i}`}' in src
    assert 'data-testid={`button-ai-explain-mobile-${i}`}' in src
    assert "disabled={!hasMd || isDeleted}" in src
