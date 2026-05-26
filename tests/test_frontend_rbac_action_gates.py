from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
KNOWLEDGE_TSX = ROOT / "pages" / "Knowledge.tsx"
KB_DETAIL_TSX = ROOT / "pages" / "KBDetail.tsx"
DATABASE_TSX = ROOT / "pages" / "Database.tsx"
CHAT_TSX = ROOT / "pages" / "Chat.tsx"
FILE_DETAIL_TSX = ROOT / "pages" / "FileDetail.tsx"


def test_knowledge_management_controls_are_permission_gated():
    src = KNOWLEDGE_TSX.read_text(encoding="utf-8")

    assert 'import { useAuth } from "@/context/AuthContext";' in src
    assert 'const canManageKnowledge = permissions.includes("config.write");' in src
    assert 'const canRunKnowledgeTasks = permissions.includes("tasks.run");' in src
    assert '{canManageKnowledge && (' in src
    assert '{canRunKnowledgeTasks && needsReembed && (' in src
    assert '{canManageKnowledge && <div className="w-px bg-border" />}' in src
    assert '{canManageKnowledge && (' in src and 'data-testid={`button-delete-kb-${kbId}`}' in src
    assert '{canManageKnowledge && (' in src and 'data-testid="button-create-profile"' in src
    assert '{canManageKnowledge && (' in src and 'data-testid="button-toggle-cleanup"' in src


def test_kb_detail_admin_controls_are_permission_gated():
    src = KB_DETAIL_TSX.read_text(encoding="utf-8")

    assert 'import { useAuth } from "@/context/AuthContext";' in src
    assert 'const canManageKnowledge = permissions.includes("config.write");' in src
    assert 'const canRunKnowledgeTasks = permissions.includes("tasks.run");' in src
    assert 'const canBindFiles = canManageKnowledge && Boolean(meta?.chunk_profile_id);' in src
    assert '{canManageKnowledge && (' in src and 'data-testid="input-kb-edit-name"' in src
    assert '{canManageKnowledge && (' in src and 'data-testid="button-add-category"' in src
    assert '{canRunKnowledgeTasks && (' in src and 'data-testid="button-index-incremental"' in src
    assert '{canRunKnowledgeTasks && (' in src and 'data-testid="button-index-rebuild"' in src
    assert '{canManageKnowledge && (' in src and 'data-testid={`button-remove-file-${i}`}' in src
    assert 'onClick={loadPendingFiles}' in src and 'canRunKnowledgeTasks' in src


def test_database_sensitive_controls_are_permission_gated():
    src = DATABASE_TSX.read_text(encoding="utf-8")

    assert 'import { useAuth } from "@/context/AuthContext";' in src
    assert 'const canDeleteFiles = permissions.includes("files.delete");' in src
    assert 'const canDownloadFiles = permissions.includes("files.download");' in src
    assert 'const canExportFiles = permissions.includes("export.read");' in src
    assert '{canExportFiles && (' in src and 'data-testid="button-export-csv"' in src
    assert '{canDeleteFiles && (' in src and 'data-testid="button-bulk-delete"' in src
    assert '{canDeleteFiles && (' in src and 'data-testid="checkbox-include-deleted"' in src
    assert '{canDownloadFiles && (' in src and 'data-testid={`button-download-${i}`}' in src
    assert '{canDownloadFiles && (' in src and 'data-testid={`button-download-mobile-${i}`}' in src


def test_chat_persistent_conversations_require_chat_conversations_permission():
    src = CHAT_TSX.read_text(encoding="utf-8")

    assert 'const canUseConversations = permissions.includes("chat.conversations");' in src
    assert 'if (canUseConversations) {' in src and 'loadConversations();' in src
    assert 'if (!canUseConversations) return;' in src
    assert '{canUseConversations && (' in src and 'data-testid="button-new-conversation"' in src
    assert '{canUseConversations && (' in src and 'data-testid="tab-conversations"' in src
    assert 'sidebarTab === "conversations" && canUseConversations ? (' in src


def test_file_detail_uses_real_task_permission_not_rag_write():
    src = FILE_DETAIL_TSX.read_text(encoding="utf-8")

    assert 'rag.write' not in src
    assert 'const canRunTasks = permissions.includes("tasks.run");' in src
    assert 'const canModifyChunk = canRunTasks && hasMarkdown' in src
