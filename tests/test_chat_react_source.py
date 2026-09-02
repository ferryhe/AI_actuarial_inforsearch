import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
CHAT_TSX = ROOT / "pages" / "Chat.tsx"
CHAT_TYPES_TS = ROOT / "pages" / "chat" / "types.ts"
CHAT_API_TS = ROOT / "pages" / "chat" / "api.ts"
CHAT_SESSION_TS = ROOT / "pages" / "chat" / "useChatSession.ts"
CHAT_DISPLAY_NAME_TS = ROOT / "pages" / "chat" / "displayName.ts"
I18N_TS = ROOT / "hooks" / "use-i18n.ts"


def read_chat_sources() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CHAT_TSX, CHAT_TYPES_TS, CHAT_API_TS, CHAT_SESSION_TS, CHAT_DISPLAY_NAME_TS)
    )


def test_chat_page_renders_citation_quote_fallback_and_retrieved_blocks():
    src = read_chat_sources()

    assert (
        "citation.quote" in src
    ), "Chat citations should render quote fallback from native API responses"
    assert (
        "retrievedBlocks" in src
    ), "Chat page should track retrieved blocks from the query response"
    assert (
        "res.data?.retrieved_blocks" in src
    ), "Chat page should read top-level retrieved_blocks from the native chat query contract"
    assert "Retrieved blocks" in src, "Chat page should render a retrieved blocks section"


def test_chat_p1_2_extracts_api_types_and_session_hook():
    chat_src = CHAT_TSX.read_text(encoding="utf-8")
    api_src = CHAT_API_TS.read_text(encoding="utf-8")
    types_src = CHAT_TYPES_TS.read_text(encoding="utf-8")
    session_src = CHAT_SESSION_TS.read_text(encoding="utf-8")

    assert 'import { useChatSession } from "./chat/useChatSession";' in chat_src
    assert 'from "./chat/api"' in chat_src
    assert 'from "./chat/types"' in chat_src
    assert "export interface KnowledgeBase" in types_src
    assert "export async function fetchKnowledgeBases" in api_src
    assert "export async function queryChat" in api_src
    assert "export function useChatSession" in session_src
    assert "apiGet" not in chat_src
    assert "apiPost" not in chat_src
    assert "apiDelete" not in chat_src


def test_chat_sidebar_is_kb_first_and_documents_deemphasized():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert 'data-testid="kb-first-sidebar"' in src
    assert "data-testid={`kb-sidebar-option-${kb.kb_id}`}" in src
    assert 'data-testid="button-toggle-documents-panel"' in src
    assert "disabled={!canUseConversations}" in src
    assert "if (!canUseConversations) return;" in src
    assert (
        'setSidebarTab((current) => current === "documents" ? "conversations" : "documents")' in src
    )
    assert 'data-testid="tab-documents"' not in src
    assert 'data-testid="tab-conversations"' not in src


def test_chat_document_explain_posts_markdown_document_context():
    src = read_chat_sources()

    assert "/api/files/${encodeURIComponent(fileUrl)}/markdown" in src
    assert "data?: { markdown?" not in src
    assert "res.data?.markdown" not in src
    assert "sendMessage({ text: questionText, document: doc })" in src
    assert "document_content: documentContexts[0].content" in src
    assert "document_title: documentContexts[0].title" in src
    assert "document_filename: documentContexts[0].filename" in src
    assert "document_file_url: documentContexts[0].fileUrl" in src
    assert "setInput(questionText)" not in src


def test_chat_accepts_database_explain_document_route_state():
    src = read_chat_sources()

    assert 'import { useLocation } from "wouter";' in src
    assert 'import { useHistoryState } from "wouter/use-browser-location";' in src
    assert "interface ChatRouteState" in src
    assert "const routeState = useHistoryState<ChatRouteState | null>()" in src
    assert "const doc = routeState?.explainDocument" in src
    assert "void askAboutDocument(doc)" in src
    assert "navigate(location, { replace: true, state: null })" in src


def test_chat_document_sidebar_uses_multi_category_filter_and_canonical_names():
    src = read_chat_sources()

    assert "selectedDocCategories" in src
    assert 'params.append("category", category)' in src
    assert 'data-testid="doc-category-filter"' in src
    assert 'data-testid="input-doc-category"' not in src
    assert "button-toggle-doc-category" in src
    assert "button-clear-doc-categories" in src
    assert 'getChatDisplayName(doc, t("chat.document_fallback"))' in src
    assert "{doc.filename || doc.title}" not in src
    assert "doc.keywords.slice(0, 3).join" not in src


def test_chat_document_sidebar_supports_multi_document_comparison():
    src = read_chat_sources()

    assert "selectedCompareDocs" in src
    assert "toggleCompareDocument" in src
    assert "compareSelectedDocuments" in src
    assert "document_sources: documentContexts.map" in src
    assert 'setMode("comparison")' in src
    assert "chat.compare_documents" in src
    assert "chat.compare_selected_count" in src
    assert 'data-testid="button-compare-selected-documents"' in src
    assert "data-testid={`button-toggle-compare-document-${i}`}" in src
    assert 'role="button"' in src
    assert "tabIndex={0}" in src
    assert 'event.key === "Enter" || event.key === " "' in src


def test_chat_document_comparison_limits_selection_and_shows_truncation_notice():
    src = read_chat_sources()
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert "MAX_DOCUMENT_CONTEXT_SOURCES = 3" in src
    assert "current.length >= MAX_DOCUMENT_CONTEXT_SOURCES" in src
    assert "chat.compare_limit_reached" in src
    assert "chat.context_truncated_notice" in src
    assert "res.data?.metadata?.context_truncated" in src
    assert "aria-disabled={compareSelectionLimitReached}" in src
    assert "\n                              disabled={compareSelectionLimitReached}" not in src
    assert "最多选择 3 个文件" in i18n_src
    assert "已自动裁剪" in i18n_src


def test_chat_citation_links_use_react_file_routes():
    src = read_chat_sources()

    assert "buildFileDetailPath," in src
    assert "buildFilePreviewPath," in src
    assert '} from "@/lib/navigation";' in src
    assert "normalizeFileRouteHref" in src
    assert 'buildFileDetailPath(fileUrl, "/chat")' in src
    assert 'buildFilePreviewPath(fileUrl, "/chat")' in src


def test_chat_citation_actions_are_i18n_labels():
    src = read_chat_sources()
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert 't("chat.file_detail")' in src
    assert 't("chat.preview")' in src
    assert "文件详情" not in src
    assert "预览" not in src
    assert '"chat.file_detail": "File details"' in i18n_src
    assert '"chat.preview": "Preview"' in i18n_src


def test_chat_supports_agentic_rag_mode_and_endpoint_contract():
    src = read_chat_sources()
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert 'type RagMode = "standard" | "agentic"' in src
    assert 'const [ragMode, setRagMode] = useState<RagMode>("standard")' in src
    assert "manifest_profile?: string" in src
    assert "agentic_ready_manifest?" in src
    assert 'ragMode === "agentic" && selectedKbs.length === 0' in src
    assert 't("chat.agentic_requires_kb")' in src
    assert '"/api/chat/query"' in src
    assert "conversation_id: activeConvId" in src
    assert "message: text" in src
    assert 'rag_mode: "agentic"' in src
    assert "kb_ids: [agenticKb.kb_id]" in src
    assert "manifest_profile: agenticProfile" not in src
    assert "profile: agenticProfile" not in src
    assert "isChatKnowledgeBaseAvailable" in src
    assert "selectedKbs.length !== 1" in src
    assert 't("chat.agentic_requires_ready_kb")' not in src
    assert 'ragMode === "agentic" && documentInputs.length === 0' in src
    assert 'if (ragMode === "agentic")' in src
    assert "prev.includes(id) ? [] : [id]" in src
    assert "prev.filter((kbId) => isChatKnowledgeBaseAvailable" in src
    assert "data-testid={`rag-mode-option-${nextMode}`}" in src
    assert '<Sparkles className="h-3 w-3" />' in src
    assert '<Search className="h-3 w-3" />' in src
    assert 't("chat.agentic_status_ready")' not in src
    assert 't("chat.agentic_status")' not in src
    assert '"Agentic ready"' not in src
    assert "`Agentic ${" not in src
    assert '"chat.rag_mode.standard": "Standard"' in i18n_src
    assert '"chat.rag_mode.agentic": "Agentic RAG"' in i18n_src
    assert (
        '"chat.agentic_requires_kb": "Select a knowledge base before using Agentic RAG."'
        in i18n_src
    )
    assert '"chat.agentic_requires_ready_kb"' not in i18n_src
    assert '"chat.agentic_status_ready"' not in i18n_src
    assert '"chat.agentic_status"' not in i18n_src


def test_chat_agentic_kb_dropdown_labels_ready_data_sections_not_standard_chunks():
    src = read_chat_sources()
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert "section_count?: number" in src
    assert "getKbResultCountLabel" in src
    assert "kb.agentic_ready_manifest?.section_count" in src
    assert '"chat.sections_label"' in src
    assert '"chat.chunks_label"' in src
    assert 'ragMode === "agentic"' in src
    assert "const resultCountLabel = getKbResultCountLabel(kb, ragMode, t)" in src
    assert "const availabilityLabel = getKbAvailabilityLabel(kb, t)" in src
    assert 't("chat.kb_status.needs_reindex")' in src
    assert 't("chat.kb_status.building")' in src
    assert 't("chat.kb_status.ready")' in src
    assert '"需重建"' not in CHAT_TSX.read_text(encoding="utf-8")
    assert '"构建中"' not in CHAT_TSX.read_text(encoding="utf-8")
    assert '"可用"' not in CHAT_TSX.read_text(encoding="utf-8")
    assert '"chat.kb_status.needs_reindex": "Needs reindex"' in i18n_src
    assert '"chat.kb_status.building": "Building"' in i18n_src
    assert '"chat.kb_status.ready": "Ready"' in i18n_src
    assert "{resultCountLabel}" in src
    assert "{kb.chunk_count} chunks" not in src
    assert '"chat.sections_label": "{count} sections"' in i18n_src
    assert '"chat.sections_label": "{count} 个分段"' in i18n_src
    assert '"chat.chunks_label": "{count} chunks"' in i18n_src


def test_chat_reuses_wrapping_retrieval_indicators_without_showing_raw_scores():
    src = read_chat_sources()
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert "score?: number" in src
    assert "semantic_relevance_100?: number | null" in src
    assert "keyword_relevance_100?: number | null" in src
    assert "retrieval_method?: string | null" in src
    assert 'import { RetrievalIndicators } from "./chat/RetrievalIndicators";' in src
    assert src.count("<RetrievalIndicators") == 2
    assert "Score: ${formatRawScore(score)}" not in src
    assert "Score: {scoreText}" not in src
    indicator_src = (CHAT_TSX.parent / "chat" / "RetrievalIndicators.tsx").read_text(
        encoding="utf-8"
    )
    assert "flex flex-wrap items-center gap-2" in indicator_src
    assert "whitespace-nowrap" in indicator_src
    for english, chinese in (
        (
            '"chat.relevance.semantic": "Semantic relevance"',
            '"chat.relevance.semantic": "语义相关度"',
        ),
        (
            '"chat.relevance.keyword": "Keyword relevance"',
            '"chat.relevance.keyword": "关键词相关度"',
        ),
        ('"chat.relevance.method": "Retrieval method"', '"chat.relevance.method": "检索方式"'),
        (
            '"chat.retrieval_method.vector": "Semantic retrieval"',
            '"chat.retrieval_method.vector": "语义检索"',
        ),
        (
            '"chat.retrieval_method.summaries": "Summaries"',
            '"chat.retrieval_method.summaries": "摘要"',
        ),
        ('"chat.retrieval_method.titles": "Titles"', '"chat.retrieval_method.titles": "标题"'),
        (
            '"chat.retrieval_method.sections": "Sections"',
            '"chat.retrieval_method.sections": "章节"',
        ),
        (
            '"chat.retrieval_method.relations": "Relations"',
            '"chat.retrieval_method.relations": "关系"',
        ),
        (
            '"chat.retrieval_method.formulas": "Formulas"',
            '"chat.retrieval_method.formulas": "公式"',
        ),
        ('"chat.retrieval_method.tables": "Tables"', '"chat.retrieval_method.tables": "表格"'),
        (
            '"chat.retrieval_method.calculation_terms": "Calculation terms"',
            '"chat.retrieval_method.calculation_terms": "计算术语"',
        ),
        ('"chat.retrieval_method.other": "Other"', '"chat.retrieval_method.other": "其他"'),
    ):
        assert english in i18n_src
        assert chinese in i18n_src


def test_chat_maps_agentic_evidence_and_renders_tool_trace():
    src = read_chat_sources()
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert "interface AgenticToolTraceEntry" in src
    assert "function AgenticTrace" in src
    assert 'data-testid="agentic-trace"' in src
    assert "data-testid={`agentic-trace-step-${traceIndex}`}" in src
    assert "normalizeAgenticToolTrace" in src
    assert "metadata.tool_trace" in src
    assert 'res.data?.response || res.response || t("chat.agentic_no_evidence")' in src
    assert "retrieved_blocks: retrievedBlocks" in src
    assert 'rag_mode: "agentic"' in src
    assert '"chat.agentic_trace": "Agentic trace"' in i18n_src
    assert '"chat.agentic_trace_results": "{count} result(s)"' in i18n_src
    assert '"chat.agentic_trace_error": "Error: {error}"' in i18n_src
    assert (
        '"chat.agentic_no_evidence": "No evidence found in ready data for this query."' in i18n_src
    )


def test_chat_uses_one_display_name_helper_for_all_document_surfaces():
    chat_src = CHAT_TSX.read_text(encoding="utf-8")
    types_src = CHAT_TYPES_TS.read_text(encoding="utf-8")
    helper_src = CHAT_DISPLAY_NAME_TS.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert 'import { getChatDisplayName, getChatValidName } from "./chat/displayName";' in chat_src
    assert "export function getChatDisplayName" in helper_src
    assert "export function getChatValidName" in helper_src
    assert 'normalized.toLowerCase() !== "unknown"' in helper_src
    assert "source.title" in helper_src
    assert "source.filename" in helper_src
    assert "source.file_url" in helper_src
    assert "source.source_url" in helper_src
    assert "title?: string" in types_src
    assert 'getChatDisplayName(citation, t("chat.source_fallback"))' in chat_src
    assert 'getChatDisplayName(block, t("chat.document_fallback"))' in chat_src
    assert 'getChatDisplayName(doc, t("chat.document_fallback"))' in chat_src
    assert '.map((doc) => getChatDisplayName(doc, t("chat.document_fallback")))' in chat_src
    assert "title: getChatValidName(doc.title)" in chat_src
    assert "filename: getChatValidName(doc.filename)" in chat_src
    assert "title: documentContext.title" in chat_src
    assert 'getChatDisplayName(citation, "Source")' not in chat_src
    assert 'getChatDisplayName(block, "Document")' not in chat_src
    assert 'getChatDisplayName(doc, "Document")' not in chat_src
    assert i18n_src.count('"chat.source_fallback": "Source"') == 1
    assert i18n_src.count('"chat.document_fallback": "Document"') == 1
    assert i18n_src.count('"chat.source_fallback": "来源"') == 1
    assert i18n_src.count('"chat.document_fallback": "文档"') == 1
    assert "doc.filename || doc.title" not in chat_src
    assert "citation.title || citation.filename" not in chat_src
    assert 'block.filename || "unknown"' not in chat_src


def test_chat_display_name_helper_runtime_prefers_title_and_rejects_placeholders():
    project_root = ROOT.parents[1]
    runner_names = ("tsx.cmd", "tsx")
    runner = next(
        (
            root / "node_modules" / ".bin" / runner_name
            for root in (project_root, project_root.parents[1])
            for runner_name in runner_names
            if (root / "node_modules" / ".bin" / runner_name).exists()
        ),
        project_root / "node_modules" / ".bin" / "tsx",
    )
    script = """
      import { getChatDisplayName } from '__HELPER_URI__';
      const cases = [
        [getChatDisplayName({ title: ' Curated ', filename: 'original.pdf' }, 'Document'), 'Curated'],
        [getChatDisplayName({ title: ' unknown ', filename: ' original.pdf ' }, 'Document'), 'original.pdf'],
        [getChatDisplayName({ title: '', filename: 'UnKnOwN', file_url: 'https://example.test/files/report%20one.pdf?x=1' }, 'Document'), 'report one.pdf'],
        [getChatDisplayName({ source_url: '/file-detail?url=https%3A%2F%2Fexample.test%2Freports%2Fprimer%2520two.pdf' }, 'Source'), 'primer two.pdf'],
        [getChatDisplayName({ file_url: '/file/https%3A%2F%2Fexample.test%2Freports%2Froute%2520three.pdf' }, 'Document'), 'route three.pdf'],
        [getChatDisplayName({ title: '   ', filename: '  ' }, 'Document'), 'Document'],
        [getChatDisplayName({ title: 'unknown', filename: 'UNKNOWN' }, '文档'), '文档'],
      ];
      for (const [actual, expected] of cases) {
        if (actual !== expected) throw new Error(`${actual} !== ${expected}`);
      }
    """.replace("__HELPER_URI__", CHAT_DISPLAY_NAME_TS.as_uri())
    completed = subprocess.run(
        [str(runner), "--eval", script],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def _brace_block(text: str, marker: str) -> str:
    """Return the balanced ``{...}`` block whose opening brace follows ``marker``."""
    open_brace = text.index("{", text.index(marker))
    depth = 0
    for i in range(open_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace : i + 1]
    raise AssertionError(f"unbalanced braces at {marker!r}")


def test_chat_comparison_submission_is_explicit_and_failure_safe():
    chat_src = CHAT_TSX.read_text(encoding="utf-8")

    # sendMessage now reports success/failure so the comparison flow can react
    assert "async function sendMessage(options?: SendMessageOptions): Promise<boolean>" in chat_src
    # the catch path must return false (surfaced failure), not swallow it silently
    assert "return false" in _brace_block(chat_src, "catch (err")

    # compareSelectedDocuments captures the result and only clears selection on success
    assert (
        'const sent = await sendMessage({ text: questionText, documents: selectedCompareDocs, modeOverride: "comparison" });'
        in chat_src
    )
    fn_block = chat_src[
        chat_src.index("async function compareSelectedDocuments") : chat_src.index(
            "async function loadDocumentMarkdown"
        )
    ]
    assert "await sendMessage" in fn_block
    # selection is cleared strictly inside the success branch (nested in if(sent)),
    # never unconditionally after send — the core regression this issue fixes
    sent_block = _brace_block(fn_block, "if (sent) {")
    assert "setSelectedCompareDocs([])" in sent_block
    assert 'setMode("comparison")' in sent_block
    assert 'setSidebarTab("conversations")' in sent_block


def test_chat_comparison_bar_lives_in_stable_region_not_scroll_area():
    chat_src = CHAT_TSX.read_text(encoding="utf-8")

    assert 'data-testid="compare-documents-bar"' in chat_src
    # the old in-scroll bar styling is gone, replaced by a stable footer
    assert "mx-1 mb-2 rounded-lg border border-border bg-muted/40 p-2" not in chat_src
    assert "border-t border-border bg-card/80 backdrop-blur-sm p-2 space-y-2" in chat_src
    # the bar renders after the scrollable document list, i.e. in a stable footer region
    assert chat_src.index("{documents.map((doc, i) =>") < chat_src.index(
        'data-testid="compare-documents-bar"'
    )


def test_chat_comparison_button_states_zero_one_two_plus_and_sending():
    chat_src = CHAT_TSX.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    # 0 documents -> no comparison action/bar rendered
    assert "{selectedCompareDocs.length > 0 && (" in chat_src
    # 1 document -> disabled (native HTML disabled) with an explicit reason
    assert "disabled={sending || selectedCompareDocs.length < 2}" in chat_src
    assert (
        'aria-describedby={selectedCompareDocs.length < 2 ? "compare-disabled-reason" : undefined}'
        in chat_src
    )
    assert 'id="compare-disabled-reason"' in chat_src
    assert "{selectedCompareDocs.length < 2 && (" in chat_src
    # 2-3 documents -> enabled styling
    assert "selectedCompareDocs.length >= 2 && !sending" in chat_src
    # sending -> disabled (prevents double submit) + pending label
    assert "aria-busy={sending}" in chat_src
    assert '{sending ? t("chat.compare_sending") : t("chat.compare_documents")}' in chat_src
    assert (
        'aria-label={sending ? t("chat.compare_sending") : t("chat.compare_documents")}' in chat_src
    )
    # pending label exists in both locales
    assert '"chat.compare_sending": "Sending…"' in i18n_src
    assert '"chat.compare_sending": "发送中…"' in i18n_src


def test_chat_comparison_fourth_document_rejected_with_limit_explanation():
    chat_src = CHAT_TSX.read_text(encoding="utf-8")
    types_src = CHAT_TYPES_TS.read_text(encoding="utf-8")
    i18n_src = I18N_TS.read_text(encoding="utf-8")

    assert "MAX_DOCUMENT_CONTEXT_SOURCES = 3" in types_src
    assert "current.length >= MAX_DOCUMENT_CONTEXT_SOURCES" in chat_src
    assert 'setErrorMsg(t("chat.compare_limit_reached"))' in chat_src
    assert "aria-disabled={compareSelectionLimitReached}" in chat_src
    assert '"chat.compare_limit_reached": "Select up to 3 files."' in i18n_src
    assert '"chat.compare_limit_reached": "最多选择 3 个文件。"' in i18n_src


def test_chat_comparison_accessible_names_clear_and_submit():
    chat_src = CHAT_TSX.read_text(encoding="utf-8")

    assert 'data-testid="compare-selected-count"' in chat_src
    assert (
        't("chat.compare_selected_count").replace("{count}", String(selectedCompareDocs.length))'
        in chat_src
    )
    assert 'aria-label={t("chat.clear_compare_selection")}' in chat_src
    assert 'data-testid="button-clear-compare-documents"' in chat_src
    assert 'data-testid="button-compare-selected-documents"' in chat_src
    assert 't("chat.compare_requires_two")' in chat_src
