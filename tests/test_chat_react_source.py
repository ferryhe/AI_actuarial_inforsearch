from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
CHAT_TSX = ROOT / "pages" / "Chat.tsx"
I18N_TS = ROOT / "hooks" / "use-i18n.ts"


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
    assert "document_content: documentContexts[0].content" in src
    assert "document_filename: documentContexts[0].filename" in src
    assert "document_file_url: documentContexts[0].fileUrl" in src
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


def test_chat_document_sidebar_supports_multi_document_comparison():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert "selectedCompareDocs" in src
    assert "toggleCompareDocument" in src
    assert "compareSelectedDocuments" in src
    assert "document_sources: documentContexts.map" in src
    assert "setMode(\"comparison\")" in src
    assert "chat.compare_documents" in src
    assert "chat.compare_selected_count" in src
    assert 'data-testid="button-compare-selected-documents"' in src
    assert 'data-testid={`button-toggle-compare-document-${i}`}' in src
    assert 'role="button"' in src
    assert "tabIndex={0}" in src
    assert 'event.key === "Enter" || event.key === " "' in src


def test_chat_document_comparison_limits_selection_and_shows_truncation_notice():
    src = CHAT_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert "MAX_DOCUMENT_CONTEXT_SOURCES = 3" in src
    assert "current.length >= MAX_DOCUMENT_CONTEXT_SOURCES" in src
    assert "chat.compare_limit_reached" in src
    assert "chat.context_truncated_notice" in src
    assert "res.data?.metadata?.context_truncated" in src
    assert "aria-disabled={compareSelectionLimitReached}" in src
    assert '\n                              disabled={compareSelectionLimitReached}' not in src
    assert "最多选择 3 个文件" in i18n_src
    assert "已自动裁剪" in i18n_src


def test_chat_citation_links_use_react_file_routes():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert 'import { buildFileDetailPath, buildFilePreviewPath } from "@/lib/navigation";' in src
    assert "normalizeFileRouteHref" in src
    assert "buildFileDetailPath(fileUrl, \"/chat\")" in src
    assert "buildFilePreviewPath(fileUrl, \"/chat\")" in src


def test_chat_citation_actions_are_i18n_labels():
    src = CHAT_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert 't("chat.file_detail")' in src
    assert 't("chat.preview")' in src
    assert '文件详情' not in src
    assert '预览' not in src
    assert '"chat.file_detail": "File details"' in i18n_src
    assert '"chat.preview": "Preview"' in i18n_src


def test_chat_supports_agentic_rag_mode_and_endpoint_contract():
    src = CHAT_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert 'type RagMode = "standard" | "agentic"' in src
    assert 'const [ragMode, setRagMode] = useState<RagMode>("standard")' in src
    assert "manifest_profile?: string" in src
    assert "agentic_ready_manifest?" in src
    assert "ragMode === \"agentic\" && selectedKbs.length === 0" in src
    assert 't("chat.agentic_requires_kb")' in src
    assert '"/api/chat/query"' in src
    assert "conversation_id: activeConvId" in src
    assert "message: text" in src
    assert 'rag_mode: "agentic"' in src
    assert "kb_ids: [agenticKb.kb_id]" in src
    assert "manifest_profile: agenticProfile" in src
    assert "profile: agenticProfile" in src
    assert "isAgenticKbReady" in src
    assert "selectedKbs.length !== 1" in src
    assert 't("chat.agentic_requires_ready_kb")' in src
    assert "ragMode === \"agentic\" && documentInputs.length === 0" in src
    assert 'if (ragMode === "agentic")' in src
    assert "prev.includes(id) ? [] : [id]" in src
    assert "prev.filter((kbId) => isAgenticKbReady" in src
    assert 'data-testid={`rag-mode-option-${nextMode}`}' in src
    assert '<Sparkles className="h-3 w-3" />' in src
    assert '<Search className="h-3 w-3" />' in src
    assert '"chat.rag_mode.standard": "Standard"' in i18n_src
    assert '"chat.rag_mode.agentic": "Agentic RAG"' in i18n_src
    assert '"chat.agentic_requires_kb": "Select a knowledge base before using Agentic RAG."' in i18n_src
    assert '"chat.agentic_requires_ready_kb": "Select one knowledge base with a ready Agentic manifest."' in i18n_src


def test_chat_maps_agentic_evidence_and_renders_tool_trace():
    src = CHAT_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert "interface AgenticToolTraceEntry" in src
    assert "function AgenticTrace" in src
    assert 'data-testid="agentic-trace"' in src
    assert 'data-testid={`agentic-trace-step-${traceIndex}`}' in src
    assert "normalizeAgenticToolTrace" in src
    assert "metadata.tool_trace" in src
    assert 'res.data?.response || res.response || t("chat.agentic_no_evidence")' in src
    assert "retrieved_blocks: retrievedBlocks" in src
    assert 'rag_mode: "agentic"' in src
    assert '"chat.agentic_trace": "Agentic trace"' in i18n_src
    assert '"chat.agentic_trace_results": "{count} result(s)"' in i18n_src
    assert '"chat.agentic_trace_error": "Error: {error}"' in i18n_src
    assert '"chat.agentic_no_evidence": "No evidence found in ready data for this query."' in i18n_src
