from __future__ import annotations

from pathlib import Path

from ai_actuarial.rag.config import RAGConfig
from ai_actuarial.rag.kb_index import (
    reconcile_legacy_kb_binding,
    reconcile_legacy_kb_bindings,
    resolve_kb_bound_chunks,
)
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.storage import Storage


def _seed_legacy_kb(tmp_path: Path, *, kb_id: str, drifted_profile: bool = False) -> Storage:
    storage = Storage(str(tmp_path / f"{kb_id}.db"))
    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.storage = storage
    manager.config = RAGConfig(data_dir=str(tmp_path / f"{kb_id}-rag"))
    manager.embedding_generator = None
    manager._ensure_rag_tables()

    file_url = f"https://example.test/{kb_id}.pdf"
    storage.insert_file(
        file_url,
        f"hash-{kb_id}",
        kb_id,
        "test",
        None,
        f"{kb_id}.pdf",
        f"{kb_id}.pdf",
        1,
        "application/pdf",
    )
    profile = storage.create_chunk_profile(
        name=f"profile-{kb_id}",
        chunk_size=100,
        chunk_overlap=10,
        splitter="semantic",
        tokenizer="cl100k_base",
        version="v1",
    )
    chunk_set = storage.get_or_create_file_chunk_set(
        file_url=file_url,
        profile_id=str(profile["profile_id"]),
        markdown_hash="markdown-v1",
        profile_config_hash=str(profile["config_hash"]),
        status="building",
    )
    storage.replace_global_chunks(
        chunk_set_id=str(chunk_set["chunk_set_id"]),
        chunks=[
            {
                "chunk_index": 0,
                "content": "legacy persisted content",
                "token_count": 3,
                "section_hierarchy": "Legacy",
            }
        ],
    )
    storage._conn.execute(
        "UPDATE file_chunk_sets SET status = 'ready', chunk_count = 1 WHERE chunk_set_id = ?",
        (chunk_set["chunk_set_id"],),
    )
    manager.create_kb(
        kb_id=kb_id,
        name=kb_id,
        kb_mode="manual",
        chunk_profile_id=("missing-profile" if drifted_profile else profile["profile_id"]),
        embedding_provider="local",
        embedding_model="test",
        embedding_dimension=3,
        embedding_identity_key="test-identity",
    )
    manager.add_files_to_kb(kb_id, [file_url])
    storage._conn.commit()
    return storage


def test_resolver_reconstructs_empty_legacy_bindings_and_audits(tmp_path: Path) -> None:
    storage = _seed_legacy_kb(tmp_path, kb_id="legacy")
    try:
        snapshot = resolve_kb_bound_chunks(storage, "legacy")

        assert snapshot["bound_file_count"] == 1
        assert snapshot["bound_chunk_count"] == 1
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?", ("legacy",)
            ).fetchone()[0]
            == 1
        )
        events = storage._conn.execute(
            "SELECT event_type FROM audit_events WHERE resource = ? ORDER BY id",
            ("knowledge_base:legacy",),
        ).fetchall()
        assert [row[0] for row in events] == ["kb_legacy_bindings_reconstructed"]

        resolve_kb_bound_chunks(storage, "legacy")
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM audit_events WHERE resource = ?",
                ("knowledge_base:legacy",),
            ).fetchone()[0]
            == 1
        )
    finally:
        storage.close()


def test_resolver_repairs_missing_profile_before_reconstructing_bindings(tmp_path: Path) -> None:
    storage = _seed_legacy_kb(tmp_path, kb_id="drifted", drifted_profile=True)
    try:
        resolve_kb_bound_chunks(storage, "drifted")

        profile_id = storage._conn.execute(
            "SELECT profile_id FROM file_chunk_sets LIMIT 1"
        ).fetchone()[0]
        assert (
            storage._conn.execute(
                "SELECT chunk_profile_id FROM rag_knowledge_bases WHERE kb_id = ?", ("drifted",)
            ).fetchone()[0]
            == profile_id
        )
        events = storage._conn.execute(
            "SELECT event_type FROM audit_events WHERE resource = ? ORDER BY id",
            ("knowledge_base:drifted",),
        ).fetchall()
        assert [row[0] for row in events] == [
            "kb_chunk_profile_reconciled",
            "kb_legacy_bindings_reconstructed",
        ]
    finally:
        storage.close()


def test_maintenance_reconciliation_is_dry_run_by_default_and_idempotent(
    tmp_path: Path,
) -> None:
    storage = _seed_legacy_kb(tmp_path, kb_id="maintenance")
    try:
        preview = reconcile_legacy_kb_bindings(storage, ["maintenance"])
        assert preview["dry_run"] is True
        assert preview["changed_count"] == 1
        assert (
            storage._conn.execute(
                "SELECT COUNT(*) FROM kb_chunk_bindings WHERE kb_id = ?", ("maintenance",)
            ).fetchone()[0]
            == 0
        )

        applied = reconcile_legacy_kb_binding(storage, "maintenance")
        assert applied["applied"] is True
        repeated = reconcile_legacy_kb_bindings(storage, ["maintenance"], dry_run=False)
        assert repeated["changed_count"] == 0
        assert repeated["applied_count"] == 0
    finally:
        storage.close()
