#!/usr/bin/env python3
"""Run a real-document RAG indexing integration check.

Usage:
  python scripts/run_rag_real_doc_integration.py --db-path data/index.db --limit 5
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from ai_actuarial.storage import Storage
from ai_actuarial.rag.knowledge_base import KnowledgeBaseManager
from ai_actuarial.rag.indexing import IndexingPipeline


def find_markdown_files(storage: Storage, limit: int) -> list[str]:
    rows = storage._conn.execute(
        """
        SELECT file_url
        FROM catalog_items
        WHERE markdown_content IS NOT NULL AND markdown_content != ''
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row[0] for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-doc RAG integration check")
    parser.add_argument("--db-path", default="data/index.db", help="SQLite DB path")
    parser.add_argument("--limit", type=int, default=5, help="Number of real docs to index")
    parser.add_argument("--kb-id", default="", help="KB ID to use (default: generated)")
    parser.add_argument("--keep-kb", action="store_true", help="Keep KB after run")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    storage = Storage(str(db_path))
    kb_manager = KnowledgeBaseManager(storage)

    file_urls = find_markdown_files(storage, max(1, args.limit))
    if not file_urls:
        raise SystemExit("No markdown-backed files found in catalog_items")

    kb_id = args.kb_id or f"real_doc_integration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    kb_name = f"RealDoc Integration {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    if kb_manager.get_kb(kb_id):
        kb_manager.delete_kb(kb_id)

    kb_manager.create_kb(kb_id=kb_id, name=kb_name, kb_mode="manual")
    kb_manager.add_files_to_kb(kb_id, file_urls)

    pipeline = IndexingPipeline(kb_manager)
    stats = pipeline.index_files(kb_id=kb_id, file_urls=file_urls, force_reindex=True)
    print("RAG real-doc integration stats:")
    for key in ["total_files", "indexed_files", "skipped_files", "error_files", "total_chunks"]:
        print(f"  {key}: {stats.get(key)}")
    if stats.get("errors"):
        print("  errors:")
        for err in stats["errors"][:10]:
            print(f"    - {err.get('file_url')}: {err.get('error')}")

    if not args.keep_kb:
        kb_manager.delete_kb(kb_id)
        print(f"Temporary KB deleted: {kb_id}")
    else:
        print(f"KB kept for inspection: {kb_id}")

    storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
