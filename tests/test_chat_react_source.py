from pathlib import Path


CHAT_TSX = Path(__file__).resolve().parents[1] / "client" / "src" / "pages" / "Chat.tsx"


def test_chat_page_renders_citation_quote_fallback_and_retrieved_blocks():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert "citation.quote" in src, "Chat citations should render quote fallback from native API responses"
    assert "retrievedBlocks" in src, "Chat page should track retrieved blocks from the query response"
    assert "res.data?.retrieved_blocks" in src, "Chat page should read top-level retrieved_blocks from the native chat query contract"
    assert "Retrieved blocks" in src, "Chat page should render a retrieved blocks section"


def test_chat_document_explain_posts_markdown_document_context():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert "/api/files/${encodeURIComponent(doc.file_url)}/markdown" in src
    assert "data?: { markdown?" not in src
    assert "res.data?.markdown" not in src
    assert "sendMessage({ text: questionText, document: doc })" in src
    assert "document_content: documentContext.content" in src
    assert "document_filename: documentContext.filename" in src
    assert "document_file_url: documentContext.fileUrl" in src
    assert "setInput(questionText)" not in src


def test_chat_accepts_database_explain_document_route_state():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert 'import { useLocation } from "wouter";' in src
    assert 'import { useHistoryState } from "wouter/use-browser-location";' in src
    assert "interface ChatRouteState" in src
    assert "const routeState = useHistoryState<ChatRouteState | null>()" in src
    assert "const doc = routeState?.explainDocument" in src
    assert "void askAboutDocument(doc)" in src
    assert "navigate(location, { replace: true, state: null })" in src


def test_chat_document_sidebar_uses_multi_category_filter_and_filename_only_rows():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert "selectedDocCategories" in src
    assert "params.append(\"category\", category)" in src
    assert "data-testid=\"doc-category-filter\"" in src
    assert "data-testid=\"input-doc-category\"" not in src
    assert "button-toggle-doc-category" in src
    assert "button-clear-doc-categories" in src
    assert "{doc.filename || doc.title}" in src
    assert "doc.keywords.slice(0, 3).join" not in src
