from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
FILE_DETAIL_TSX = ROOT / "pages" / "FileDetail.tsx"
FILE_PREVIEW_TSX = ROOT / "pages" / "FilePreview.tsx"


def test_file_detail_ai_explain_passes_loaded_markdown_to_chat():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "function explainCurrentFile()" in src
    assert 'navigate("/chat"' in src
    assert "document_content: markdown.markdown_content" in src
    assert "file_url: file.url" in src
    assert "filename," in src
    assert "title: file.title || filename" in src
    assert "category: file.category || \"\"" in src
    assert "keywords: file.keywords || []" in src
    assert 'data-testid="button-ai-explain"' in src
    assert "disabled={!canExplain}" in src


def test_file_detail_renders_markdown_with_local_renderer():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "function MarkdownRenderer" in src
    assert "<MarkdownRenderer content={markdownContent} />" in src
    assert '<pre className="whitespace-pre-wrap text-sm font-sans">{markdown?.markdown_content}</pre>' not in src


def test_file_detail_uses_permission_gates_for_mutating_actions():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "const { permissions } = useAuth()" in src
    assert 'permissions.includes("files.download")' in src
    assert 'permissions.includes("files.delete")' in src
    assert 'permissions.includes("catalog.write")' in src
    assert 'permissions.includes("markdown.write")' in src
    assert 'permissions.includes("rag.write")' in src


def test_file_detail_chunk_modal_can_bind_generated_chunks_to_kb():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert "body.profile_id = chunkProfileId" in src
    assert "body.kb_id = selectedKbId" in src
    assert "binding_mode: bindingMode" in src
    assert 'data-testid="select-file-chunk-profile"' in src
    assert 'data-testid="checkbox-file-bind-kb"' in src
    assert 'data-testid="select-file-bind-kb"' in src
    assert 'data-testid="select-file-binding-mode"' in src


def test_file_preview_passes_download_permission_to_original_pane():
    src = FILE_PREVIEW_TSX.read_text(encoding="utf-8")

    assert "function OriginalPane({ fileInfo, canDownload }" in src
    assert "canDownload={canDownload}" in src
