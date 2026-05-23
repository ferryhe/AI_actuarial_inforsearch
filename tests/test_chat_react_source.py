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
