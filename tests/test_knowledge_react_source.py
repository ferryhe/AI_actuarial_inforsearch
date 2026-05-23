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
