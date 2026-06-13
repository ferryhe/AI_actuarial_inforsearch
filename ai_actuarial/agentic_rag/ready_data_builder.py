"""Ready-data builder — L0 MVP.

Reads existing catalog_items and global_chunks from the SQLite DB
and produces the L0 ready_data artifacts:

  doc_catalog.jsonl   — document index with title, category, summary, headings
  sections.jsonl      — section-level chunks with heading_path and token_count
  ready_data_manifest.json — build metadata and counts

Usage:
  python -m ai_actuarial.agentic_rag.ready_data_builder
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest_profiles import L0_GENERAL, PROFILES

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """Resolve the SQLite DB path (same logic as config)."""
    db_path = os.getenv("DB_PATH", "data/index.db")
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(db_path)
    return db_path


# ── Schema ────────────────────────────────────────────────────────────────────

DOC_CATALOG_FIELDS = [
    "doc_id",
    "file_url",
    "title",
    "category",
    "source_site",
    "publish_date",
    "summary",
    "keywords",
    "headings",
    "rag_chunk_count",
]

SECTION_FIELDS = [
    "section_id",
    "doc_id",
    "heading_path",
    "text",
    "token_count",
]


# ── Extraction helpers ────────────────────────────────────────────────────────

def _extract_headings(chunks: list[dict]) -> list[str]:
    """Extract unique ordered headings from section_hierarchy across chunks."""
    seen: set[str] = set()
    headings: list[str] = []
    for chunk in chunks:
        hierarchy = chunk.get("section_hierarchy", "")
        if not hierarchy:
            continue
        for h in hierarchy.split(" > "):
            h = h.strip()
            if h and h not in seen:
                seen.add(h)
                headings.append(h)
    return headings


def _parse_keywords(raw: str | None) -> list[str]:
    """Parse keywords from JSON string or comma-separated text."""
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("["):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return [k.strip() for k in raw.split(",") if k.strip()]


# ── Builder ───────────────────────────────────────────────────────────────────

def build_l0(
    db_path: str | None = None,
    output_dir: str | None = None,
    profile: str = "general",
) -> dict:
    """Build L0 ready_data artifacts from catalog_items + global_chunks.

    Args:
        db_path: Path to SQLite DB. Defaults to env DB_PATH or data/index.db.
        output_dir: Output directory. Defaults to data/agentic_ready_data/{profile}/.
        profile: Manifest profile key (general, regulation, formula).

    Returns:
        Manifest dict with built_at, doc_count, section_count, artifact_files.
    """
    db_path = db_path or get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    profile_def = PROFILES.get(profile, L0_GENERAL)
    if output_dir is None:
        output_dir = os.path.join("data", "agentic_ready_data", profile, profile_def.version)
    os.makedirs(output_dir, exist_ok=True)

    now_utc = datetime.now(timezone.utc).isoformat()

    # ── 1. Build doc_catalog.jsonl ────────────────────────────────────────
    catalog_rows = conn.execute(
        """SELECT c.file_url, f.title, c.category, c.summary, c.keywords,
                  c.rag_chunk_count,
                  f.source_site, f.published_time
           FROM catalog_items c
           LEFT JOIN files f ON c.file_url = f.url
           WHERE c.status = 'ok'
           ORDER BY c.category, c.file_url"""
    ).fetchall()

    # Collect per-doc chunks for heading extraction
    file_urls = [r["file_url"] for r in catalog_rows]
    placeholders = ",".join("?" for _ in file_urls)
    chunk_rows = (
        conn.execute(
            f"""SELECT g.chunk_id, g.content, g.token_count, g.section_hierarchy,
                       fcs.file_url
                FROM global_chunks g
                JOIN file_chunk_sets fcs ON g.chunk_set_id = fcs.chunk_set_id
                WHERE fcs.file_url IN ({placeholders})
                ORDER BY fcs.file_url, g.chunk_index""",
            file_urls,
        ).fetchall()
        if file_urls
        else []
    )

    # Group chunks by file_url
    chunks_by_file: dict[str, list[dict]] = {}
    for row in chunk_rows:
        chunks_by_file.setdefault(row["file_url"], []).append(dict(row))

    doc_catalog_path = os.path.join(output_dir, "doc_catalog.jsonl")
    doc_count = 0
    with open(doc_catalog_path, "w", encoding="utf-8") as f:
        for row in catalog_rows:
            file_url = row["file_url"]
            chunks = chunks_by_file.get(file_url, [])
            headings = _extract_headings(chunks)
            keywords = _parse_keywords(row["keywords"])

            entry = {
                "doc_id": file_url,
                "file_url": file_url,
                "title": row["title"] or file_url,
                "category": row["category"] or "general",
                "source_site": row["source_site"] or "",
                "publish_date": row["published_time"] or "",
                "summary": row["summary"] or "",
                "keywords": keywords,
                "headings": headings,
                "rag_chunk_count": row["rag_chunk_count"] or 0,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            doc_count += 1

    # ── 2. Build sections.jsonl ───────────────────────────────────────────
    section_count = 0
    sections_path = os.path.join(output_dir, "sections.jsonl")
    with open(sections_path, "w", encoding="utf-8") as f:
        for row in chunk_rows:
            file_url = row["file_url"]
            chunk_id = row["chunk_id"]
            hierarchy = row["section_hierarchy"] or ""
            heading_path = [h.strip() for h in hierarchy.split(" > ") if h.strip()]

            entry: dict[str, Any] = {
                "section_id": f"{file_url}#{chunk_id}",
                "doc_id": file_url,
                "heading_path": heading_path,
                "text": row["content"] or "",
                "token_count": row["token_count"] or 0,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            section_count += 1

    # ── 3. Build ready_data_manifest.json ─────────────────────────────────
    manifest = {
        "built_at": now_utc,
        "profile": profile,
        "profile_version": profile_def.version,
        "source_db": db_path,
        "doc_count": doc_count,
        "section_count": section_count,
        "artifact_files": ["doc_catalog.jsonl", "sections.jsonl", "ready_data_manifest.json"],
        "schema_versions": {
            "doc_catalog_fields": DOC_CATALOG_FIELDS,
            "section_fields": SECTION_FIELDS,
        },
    }
    manifest_path = os.path.join(output_dir, "ready_data_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    conn.close()
    logger.info(
        "L0 ready_data built: %d docs, %d sections → %s",
        doc_count,
        section_count,
        output_dir,
    )
    return manifest


def validate(output_dir: str) -> dict:
    """Validate built ready_data artifacts.

    Checks: files exist, JSONL lines are valid JSON, required fields present,
    doc_id references consistent between catalog and sections.
    """
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = os.path.join(output_dir, "ready_data_manifest.json")
    if not os.path.isfile(manifest_path):
        errors.append(f"manifest not found: {manifest_path}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for artifact in manifest.get("artifact_files", []):
        path = os.path.join(output_dir, artifact)
        if not os.path.isfile(path):
            errors.append(f"artifact missing: {artifact}")
        elif artifact.endswith(".jsonl"):
            # Validate JSONL: every line must parse
            bad_lines = 0
            with open(path, "r", encoding="utf-8") as af:
                for i, line in enumerate(af, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                    except json.JSONDecodeError:
                        bad_lines += 1
                        if bad_lines <= 3:
                            errors.append(f"{artifact}:{i} invalid JSON")
            if bad_lines:
                errors.append(f"{artifact}: {bad_lines} invalid JSON lines")

        elif artifact.endswith(".json"):
            try:
                with open(path, "r", encoding="utf-8") as af:
                    json.load(af)
            except json.JSONDecodeError as e:
                errors.append(f"{artifact}: invalid JSON: {e}")

    # Cross-reference: doc_ids in sections must exist in catalog
    doc_catalog_path = os.path.join(output_dir, "doc_catalog.jsonl")
    sections_path = os.path.join(output_dir, "sections.jsonl")
    if os.path.isfile(doc_catalog_path) and os.path.isfile(sections_path):
        catalog_doc_ids: set[str] = set()
        with open(doc_catalog_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                catalog_doc_ids.add(json.loads(line).get("doc_id", ""))

        section_doc_ids: set[str] = set()
        with open(sections_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                section_doc_ids.add(json.loads(line).get("doc_id", ""))

        orphan_sections = section_doc_ids - catalog_doc_ids
        if orphan_sections:
            errors.append(
                f"{len(orphan_sections)} section doc_ids not in catalog "
                f"(e.g. {list(orphan_sections)[:3]})"
            )

        docs_without_sections = catalog_doc_ids - section_doc_ids
        if docs_without_sections:
            warnings.append(
                f"{len(docs_without_sections)} docs have no sections "
                f"(e.g. {list(docs_without_sections)[:3]})"
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    import argparse

    parser = argparse.ArgumentParser(description="Build L0 Agentic RAG ready_data")
    parser.add_argument("--db", default=None, help="SQLite DB path")
    parser.add_argument(
        "--output-dir", default=None, help="Output directory for ready_data"
    )
    parser.add_argument(
        "--profile",
        default="general",
        choices=["general", "regulation", "formula"],
        help="Manifest profile",
    )
    parser.add_argument("--validate", action="store_true", help="Validate after build")
    args = parser.parse_args()

    manifest = build_l0(
        db_path=args.db,
        output_dir=args.output_dir,
        profile=args.profile,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    if args.validate:
        result = validate(
            args.output_dir
            or os.path.join("data", "agentic_ready_data", args.profile, "1")
        )
        status = "✅ valid" if result["valid"] else "❌ invalid"
        print(f"\nValidation: {status}")
        if result["errors"]:
            for e in result["errors"]:
                print(f"  ERROR: {e}")
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"  WARN:  {w}")


if __name__ == "__main__":
    main()
