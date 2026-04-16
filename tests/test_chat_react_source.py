from pathlib import Path


CHAT_TSX = Path(__file__).resolve().parents[1] / "client" / "src" / "pages" / "Chat.tsx"


def test_chat_page_renders_citation_quote_fallback_and_retrieved_blocks():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert "citation.quote" in src, "Chat citations should render quote fallback from native API responses"
    assert "retrievedBlocks" in src, "Chat page should track retrieved blocks from the query response"
    assert "res.data?.retrieved_blocks" in src, "Chat page should read top-level retrieved_blocks from the native chat query contract"
    assert "Retrieved blocks" in src, "Chat page should render a retrieved blocks section like the legacy Flask UI"
