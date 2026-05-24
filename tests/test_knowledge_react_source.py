from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src" / "pages"
KNOWLEDGE_TSX = ROOT / "Knowledge.tsx"
KB_DETAIL_TSX = ROOT / "KBDetail.tsx"


def test_knowledge_pages_surface_reembed_action_for_embedding_mismatch():
    knowledge_src = KNOWLEDGE_TSX.read_text(encoding="utf-8")
    detail_src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "handleReembedKB" in knowledge_src
    assert 'data-testid={`button-reembed-kb-${kbId}`}' in knowledge_src
    assert "kb.needs_reindex || kb.embedding_compatible === false" in knowledge_src

    assert "needsEmbeddingRebuild" in detail_src
    assert 'data-testid="banner-embedding-mismatch"' in detail_src
    assert 'data-testid="button-reembed-current-embedding"' in detail_src


def test_knowledge_create_uses_backend_embedding_configuration_only():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert '"/api/config/ai-models"' not in src
    assert "embeddingModels" not in src
    assert "embedding_model: kbForm" not in src
    assert 'data-testid="select-kb-embedding"' not in src
    assert 'data-testid="text-kb-backend-embedding"' not in src
    assert "currentEmbeddingLabel" not in src
    assert "current_embeddings" in src


def test_knowledge_create_supports_document_and_category_multiselects():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert "/api/rag/files/selectable?" in src
    assert '"/api/rag/categories/mapping"' in src
    assert 'data-testid="kb-document-picker"' in src
    assert 'data-testid="kb-category-picker"' in src
    assert "file_urls: kbForm.kb_mode === \"manual\" ? kbForm.file_urls : []" in src
    assert "categories: kbForm.categories" in src
    assert "toggleKbFile" in src
    assert "toggleKbCategory" in src
    assert 'data-testid="input-kb-categories"' not in src
    assert '"/api/rag/categories/stats"' in src
    assert 'data-testid="kb-category-stats"' in src
    assert 'data-testid="button-submit-kb-index"' in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(finalKbId)}/index`" in src


def test_knowledge_create_supports_select_all_and_all_mode():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert '<option value="all">{t("knowledge.mode_all")}</option>' in src
    assert "kbForm.kb_mode === \"all\"" in src
    assert "handleSelectAllKbFiles" in src
    assert 'data-testid="button-select-all-kb-files"' in src
    assert "selectableFiles.every((file) => kbForm.file_urls.includes(file.url))" in src


def test_knowledge_create_surfaces_create_and_index_errors():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert "ApiError" in src
    assert "kbActionError" in src
    assert "setKbActionError" in src
    assert "kbActionNotice" in src
    assert 'data-testid="alert-kb-action-error"' in src
    assert 'data-testid="alert-kb-action-notice"' in src
    assert "err instanceof ApiError" in src
    assert 'type="button"' in src
    assert "indexFailed" in src
    assert "knowledge.create_index_partial_error" in src


def test_knowledge_create_uses_existing_chunk_profile_not_inline_chunk_settings():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert 'data-testid="select-kb-chunk-profile"' in src
    assert "chunk_profile_id: kbForm.chunk_profile_id" in src
    assert 'params.set("profile_id", kbForm.chunk_profile_id)' in src
    assert 'data-testid="input-kb-chunk-size"' not in src
    assert 'data-testid="input-kb-chunk-overlap"' not in src
    assert "chunk_size: kbForm.chunk_size" not in src
    assert "chunk_overlap: kbForm.chunk_overlap" not in src


def test_kb_detail_bind_dialog_uses_kb_chunk_profile_and_chunk_bindings():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "chunk_profile_id?: string" in src
    assert 'params.set("profile_id", meta.chunk_profile_id)' in src
    assert "chunk_set_id?: string" in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/bindings`" in src
    assert "bindings: selectedBindFiles.map" in src
    assert "chunk_set_id: file.chunk_set_id" in src
    assert "canBindFiles" in src
    assert "disabled={!canBindFiles}" in src
    assert "if (!canBindFiles) return;" in src


def test_kb_detail_manual_mode_can_add_files_with_select_all_and_category_index_prompt():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert "isManualMode" in src
    assert "handleSelectAllBindFiles" in src
    assert 'data-testid="button-select-all-bind-files"' in src
    assert "`/api/rag/knowledge-bases/${encodeURIComponent(kbId)}/files`" in src
    assert "file_urls: selectedBindFiles" in src
    assert "meta.kb_mode === \"manual\"" in src
    assert 'data-testid="banner-category-index-required"' in src
