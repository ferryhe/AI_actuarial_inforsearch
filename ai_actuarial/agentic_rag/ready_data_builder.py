"""Ready-data builder for Agentic RAG ready_data artifacts.

Reads existing catalog_items and global_chunks from the SQLite DB
and produces ready_data artifacts:

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
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .manifest_profiles import PROFILES

try:
    from ai_actuarial.config import settings

    _DB_PATH_FROM_SETTINGS = settings.DB_PATH
except ImportError:
    _DB_PATH_FROM_SETTINGS = None

logger = logging.getLogger(__name__)


def get_db_path() -> str:
    """Resolve the SQLite DB path from settings, env, or default."""
    if _DB_PATH_FROM_SETTINGS:
        db_path = _DB_PATH_FROM_SETTINGS
    else:
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

TITLE_ALIAS_FIELDS = [
    "doc_id",
    "file_url",
    "title",
    "aliases",
    "identifiers",
    "document_numbers",
    "rule_numbers",
]

DOC_SUMMARY_FIELDS = [
    "doc_id",
    "file_url",
    "title",
    "category",
    "summary",
]

STRUCTURED_SECTION_FIELDS = [
    "section_id",
    "doc_id",
    "file_url",
    "title",
    "heading_path",
    "heading",
    "text",
    "token_count",
    "document_aliases",
]

RELATION_FIELDS = [
    "relation_type",
    "doc_id",
    "file_url",
    "title",
    "alias",
    "section_id",
    "section_heading",
    "target_type",
    "target_id",
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


def _unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _extract_identifier_parts(title: str, file_url: str) -> tuple[list[str], list[str], list[str]]:
    document_numbers: list[str] = []
    rule_numbers: list[str] = []
    for match in re.finditer(r"(?:第\s*)?([0-9]+)\s*号", title, flags=re.IGNORECASE):
        document_numbers.append(match.group(1))
    for match in re.finditer(
        r"\b(?:rule|article)\s*[-#: ]\s*([A-Za-z0-9_.-]+)",
        title,
        flags=re.IGNORECASE,
    ):
        rule_numbers.append(match.group(1))
    identifiers: list[str] = [*document_numbers, *rule_numbers]
    for match in re.finditer(
        r"\b(?:regulation|guideline|standard)\s*[-#: ]\s*([A-Za-z0-9_.-]+)",
        title,
        flags=re.IGNORECASE,
    ):
        identifiers.append(match.group(1))
    parsed = urlparse(file_url)
    stem = Path(parsed.path or file_url).stem
    if stem:
        identifiers.append(stem)
    return _unique_strings(identifiers), _unique_strings(document_numbers), _unique_strings(rule_numbers)


def _build_doc_aliases(entry: dict[str, Any]) -> tuple[list[str], list[str], list[str], list[str]]:
    title = str(entry.get("title") or "").strip()
    file_url = str(entry.get("file_url") or entry.get("doc_id") or "").strip()
    identifiers, document_numbers, rule_numbers = _extract_identifier_parts(title, file_url)
    aliases = [title, *identifiers]
    return _unique_strings(aliases), identifiers, document_numbers, rule_numbers


def _section_heading(heading_path: list[str]) -> str:
    return heading_path[-1] if heading_path else ""


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return bool(row)


# ── Builder ───────────────────────────────────────────────────────────────────

def build_l0(
    db_path: str | None = None,
    output_dir: str | None = None,
    profile: str = "general",
    kb_id: str | None = None,
) -> dict:
    """Build L0 ready_data artifacts from catalog_items + global_chunks.

    Args:
        db_path: Path to SQLite DB. Defaults to env DB_PATH or data/index.db.
        output_dir: Output directory. Defaults to data/agentic_ready_data/{profile}/.
        profile: Manifest profile key (general, regulation, formula).
        kb_id: Optional knowledge-base ID; when set, only files in that KB are exported.

    Returns:
        Manifest dict with built_at, doc_count, section_count, artifact_files.
    """
    db_path = db_path or get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if profile not in PROFILES:
        raise ValueError(
            f"Unknown profile {profile!r}. Use one of: {', '.join(PROFILES)}"
        )
    profile_def = PROFILES[profile]

    if profile not in {"general", "regulation"}:
        raise NotImplementedError(
            f"Profile {profile!r} is not yet implemented. "
            "Only 'general' (L0) and 'regulation' (L1) are supported."
        )
    if output_dir is None:
        if kb_id:
            safe_kb_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in kb_id)
            output_dir = os.path.join("data", "agentic_ready_data", "kbs", safe_kb_id, profile, profile_def.version)
        else:
            output_dir = os.path.join("data", "agentic_ready_data", profile, profile_def.version)
    os.makedirs(output_dir, exist_ok=True)

    now_utc = datetime.now(timezone.utc).isoformat()

    # ── 1. Build doc_catalog.jsonl ────────────────────────────────────────
    kb_join = ""
    where_params: list[Any] = []
    if kb_id:
        kb_join = "JOIN rag_kb_files kf ON kf.file_url = c.file_url AND kf.kb_id = ?"
        where_params.append(kb_id)
    catalog_rows = conn.execute(
        f"""SELECT c.file_url, f.title, c.category, c.summary, c.keywords,
                   c.rag_chunk_count,
                   f.source_site, f.published_time
            FROM catalog_items c
            {kb_join}
            LEFT JOIN files f ON c.file_url = f.url
            WHERE c.status = 'ok'
            ORDER BY c.category, c.file_url""",
        where_params,
    ).fetchall()

    # Collect per-doc chunks for heading extraction
    file_urls = [r["file_url"] for r in catalog_rows]
    placeholders = ",".join("?" for _ in file_urls)
    chunk_rows = []
    if file_urls:
        use_bound_chunk_sets = bool(
            kb_id
            and _table_exists(conn, "kb_chunk_bindings")
            and conn.execute(
                "SELECT 1 FROM kb_chunk_bindings WHERE kb_id = ? LIMIT 1",
                (kb_id,),
            ).fetchone()
        )
        if use_bound_chunk_sets:
            chunk_rows = conn.execute(
                f"""SELECT g.chunk_id, g.content, g.token_count, g.section_hierarchy,
                           fcs.file_url
                    FROM global_chunks g
                    JOIN file_chunk_sets fcs ON g.chunk_set_id = fcs.chunk_set_id
                    JOIN kb_chunk_bindings b
                      ON b.chunk_set_id = fcs.chunk_set_id
                     AND b.file_url = fcs.file_url
                     AND b.kb_id = ?
                    WHERE fcs.file_url IN ({placeholders})
                    ORDER BY fcs.file_url, g.chunk_index""",
                [kb_id, *file_urls],
            ).fetchall()
        else:
            chunk_rows = conn.execute(
                f"""SELECT g.chunk_id, g.content, g.token_count, g.section_hierarchy,
                           fcs.file_url
                    FROM global_chunks g
                    JOIN file_chunk_sets fcs ON g.chunk_set_id = fcs.chunk_set_id
                    WHERE fcs.file_url IN ({placeholders})
                    ORDER BY fcs.file_url, g.chunk_index""",
                file_urls,
            ).fetchall()

    # Group chunks by file_url
    chunks_by_file: dict[str, list[dict]] = {}
    for row in chunk_rows:
        chunks_by_file.setdefault(row["file_url"], []).append(dict(row))

    doc_catalog_path = os.path.join(output_dir, "doc_catalog.jsonl")
    doc_count = 0
    catalog_entries: list[dict[str, Any]] = []
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
            catalog_entries.append(entry)
            doc_count += 1

    # ── 2. Build sections.jsonl ───────────────────────────────────────────
    section_count = 0
    sections_path = os.path.join(output_dir, "sections.jsonl")
    section_entries: list[dict[str, Any]] = []
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
            if profile == "regulation":
                section_entries.append(entry)
            section_count += 1

    alias_rows: list[dict[str, Any]] = []
    aliases_by_doc: dict[str, list[str]] = {}
    if profile == "regulation":
        for entry in catalog_entries:
            aliases, identifiers, document_numbers, rule_numbers = _build_doc_aliases(entry)
            aliases_by_doc[entry["doc_id"]] = aliases
            alias_rows.append(
                {
                    "doc_id": entry["doc_id"],
                    "file_url": entry["file_url"],
                    "title": entry["title"],
                    "aliases": aliases,
                    "identifiers": identifiers,
                    "document_numbers": document_numbers,
                    "rule_numbers": rule_numbers,
                }
            )
        title_aliases_path = os.path.join(output_dir, "title_aliases.jsonl")
        with open(title_aliases_path, "w", encoding="utf-8") as f:
            for row in alias_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        doc_summaries_path = os.path.join(output_dir, "doc_summaries.jsonl")
        with open(doc_summaries_path, "w", encoding="utf-8") as f:
            for entry in catalog_entries:
                f.write(
                    json.dumps(
                        {
                            "doc_id": entry["doc_id"],
                            "file_url": entry["file_url"],
                            "title": entry["title"],
                            "category": entry["category"],
                            "summary": entry["summary"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        catalog_by_doc = {entry["doc_id"]: entry for entry in catalog_entries}
        relations: list[dict[str, Any]] = []
        structured_sections_path = os.path.join(output_dir, "sections_structured.jsonl")
        with open(structured_sections_path, "w", encoding="utf-8") as f:
            for section in section_entries:
                doc = catalog_by_doc.get(section["doc_id"], {})
                heading_path = section.get("heading_path") or []
                heading = _section_heading(heading_path)
                structured = {
                    "section_id": section["section_id"],
                    "doc_id": section["doc_id"],
                    "file_url": doc.get("file_url", section["doc_id"]),
                    "title": doc.get("title", section["doc_id"]),
                    "heading_path": heading_path,
                    "heading": heading,
                    "text": section.get("text", ""),
                    "token_count": section.get("token_count", 0),
                    "document_aliases": aliases_by_doc.get(section["doc_id"], []),
                }
                f.write(json.dumps(structured, ensure_ascii=False) + "\n")
                relations.append(
                    {
                        "relation_type": "document_has_section",
                        "doc_id": structured["doc_id"],
                        "file_url": structured["file_url"],
                        "title": structured["title"],
                        "section_id": structured["section_id"],
                        "section_heading": heading,
                        "target_type": "section",
                        "target_id": structured["section_id"],
                    }
                )

        for row in alias_rows:
            for alias in row["aliases"]:
                relations.append(
                    {
                        "relation_type": "alias_of",
                        "doc_id": row["doc_id"],
                        "file_url": row["file_url"],
                        "title": row["title"],
                        "alias": alias,
                        "target_type": "document",
                        "target_id": row["doc_id"],
                    }
                )

        relations_path = os.path.join(output_dir, "relations_graph.json")
        with open(relations_path, "w", encoding="utf-8") as f:
            json.dump({"relations": relations}, f, indent=2, ensure_ascii=False)

    # ── 3. Build ready_data_manifest.json ─────────────────────────────────
    profile_def_artifacts = profile_def.artifacts
    manifest = {
        "built_at": now_utc,
        "profile": profile,
        "profile_version": profile_def.version,
        "kb_id": kb_id or "",
        "scope": "knowledge_base" if kb_id else "global",
        "source_db": db_path,
        "output_dir": output_dir,
        "doc_count": doc_count,
        "section_count": section_count,
        "artifact_files": profile_def_artifacts,
        "schema_versions": {
            "doc_catalog_fields": DOC_CATALOG_FIELDS,
            "section_fields": SECTION_FIELDS,
            "title_alias_fields": TITLE_ALIAS_FIELDS,
            "doc_summary_fields": DOC_SUMMARY_FIELDS,
            "structured_section_fields": STRUCTURED_SECTION_FIELDS,
            "relation_fields": RELATION_FIELDS,
        },
    }
    manifest_path = os.path.join(output_dir, "ready_data_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    conn.close()
    logger.info(
        "%s ready_data built: %d docs, %d sections → %s",
        profile,
        doc_count,
        section_count,
        output_dir,
    )
    return manifest


def _safe_jsonl_load(file_path: str) -> tuple[list[dict], list[str]]:
    """Load a JSONL file, returning parsed entries and parse-error line numbers."""
    entries: list[dict] = []
    errors: list[str] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                errors.append(f"{os.path.basename(file_path)}:{i} invalid JSON")
                if len(errors) > 3:
                    break
    return entries, errors


def _manifest_artifact_path(output_dir: str, artifact: Any) -> tuple[str | None, str | None]:
    artifact_text = str(artifact or "").strip()
    if not artifact_text:
        return None, "artifact path is empty"
    candidate = Path(artifact_text)
    if candidate.is_absolute():
        return None, f"artifact path escapes output_dir: {artifact_text}"
    root = Path(output_dir).resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, f"artifact path escapes output_dir: {artifact_text}"
    return str(resolved), None


def validate(output_dir: str) -> dict:
    """Validate built ready_data artifacts.

    Checks: files exist, JSONL lines are valid JSON,
    doc_id references consistent between catalog and sections.
    """
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = os.path.join(output_dir, "ready_data_manifest.json")
    if not os.path.isfile(manifest_path):
        errors.append(f"manifest not found: {manifest_path}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"ready_data_manifest.json: invalid JSON: {e}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    artifact_paths: dict[str, str] = {}
    for artifact in manifest.get("artifact_files", []):
        artifact_text = str(artifact or "").strip()
        path, path_error = _manifest_artifact_path(output_dir, artifact)
        artifact_name = os.path.basename(artifact_text)
        if path_error:
            errors.append(path_error)
            continue
        if path and artifact_name:
            artifact_paths[artifact_name] = path
        if not os.path.isfile(path):
            errors.append(f"artifact missing: {artifact}")
        elif artifact_text.endswith(".jsonl"):
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

        elif artifact_text.endswith(".json"):
            try:
                with open(path, "r", encoding="utf-8") as af:
                    json.load(af)
            except json.JSONDecodeError as e:
                errors.append(f"{artifact}: invalid JSON: {e}")

    # Cross-reference: doc_ids in sections must exist in catalog.
    doc_catalog_path = artifact_paths.get("doc_catalog.jsonl") or os.path.join(output_dir, "doc_catalog.jsonl")
    sections_path = artifact_paths.get("sections.jsonl") or os.path.join(output_dir, "sections.jsonl")
    catalog_entries: list[dict[str, Any]] = []
    catalog_doc_ids: set[str] = set()
    if os.path.isfile(doc_catalog_path):
        catalog_entries, cat_errors = _safe_jsonl_load(doc_catalog_path)
        errors.extend(cat_errors)
        catalog_doc_ids = {e.get("doc_id", "") for e in catalog_entries}

    section_entries: list[dict[str, Any]] = []
    section_doc_ids: set[str] = set()
    section_ids: set[str] = set()
    if catalog_doc_ids and os.path.isfile(sections_path):
        section_entries, sec_errors = _safe_jsonl_load(sections_path)
        errors.extend(sec_errors)
        section_doc_ids = {e.get("doc_id", "") for e in section_entries}
        section_ids = {e.get("section_id", "") for e in section_entries if e.get("section_id")}

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

    structured_sections_path = artifact_paths.get("sections_structured.jsonl") or os.path.join(output_dir, "sections_structured.jsonl")
    structured_section_ids: set[str] = set()
    if catalog_doc_ids and os.path.isfile(structured_sections_path):
        structured_entries, structured_errors = _safe_jsonl_load(structured_sections_path)
        errors.extend(structured_errors)
        structured_doc_ids = {e.get("doc_id", "") for e in structured_entries}
        orphan_structured = structured_doc_ids - catalog_doc_ids
        if orphan_structured:
            errors.append(
                f"{len(orphan_structured)} structured section doc_ids not in catalog "
                f"(e.g. {list(orphan_structured)[:3]})"
            )
        structured_section_ids = {e.get("section_id", "") for e in structured_entries if e.get("section_id")}

    relations_path = artifact_paths.get("relations_graph.json") or os.path.join(output_dir, "relations_graph.json")
    if catalog_doc_ids and os.path.isfile(relations_path):
        try:
            with open(relations_path, "r", encoding="utf-8") as f:
                graph = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"relations_graph.json: invalid JSON: {e}")
        else:
            relations = graph.get("relations") if isinstance(graph, dict) else None
            if not isinstance(relations, list):
                errors.append("relations_graph.json: relations must be a list")
            else:
                relation_doc_ids = {
                    row.get("doc_id", "")
                    for row in relations
                    if isinstance(row, dict) and row.get("doc_id")
                }
                orphan_relation_docs = relation_doc_ids - catalog_doc_ids
                if orphan_relation_docs:
                    errors.append(
                        f"{len(orphan_relation_docs)} relation doc_ids not in catalog "
                        f"(e.g. {list(orphan_relation_docs)[:3]})"
                    )
                relation_section_ids = {
                    row.get("target_id", "")
                    for row in relations
                    if isinstance(row, dict) and row.get("target_type") == "section" and row.get("target_id")
                }
                relation_section_ids.update(
                    row.get("section_id", "")
                    for row in relations
                    if isinstance(row, dict) and row.get("section_id")
                )
                known_section_ids = section_ids | structured_section_ids
                orphan_relation_sections = relation_section_ids - known_section_ids
                if orphan_relation_sections:
                    errors.append(
                        f"{len(orphan_relation_sections)} relation section targets not in sections "
                        f"(e.g. {list(orphan_relation_sections)[:3]})"
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

    parser = argparse.ArgumentParser(description="Build Agentic RAG ready_data")
    parser.add_argument("--db", default=None, help="SQLite DB path")
    parser.add_argument(
        "--output-dir", default=None, help="Output directory for ready_data"
    )
    parser.add_argument(
        "--profile",
        default="general",
        choices=["general", "regulation"],
        help="Manifest profile",
    )
    parser.add_argument("--kb-id", default=None, help="Optional knowledge-base ID to export")
    parser.add_argument("--validate", action="store_true", help="Validate after build")
    args = parser.parse_args()

    manifest = build_l0(
        db_path=args.db,
        output_dir=args.output_dir,
        profile=args.profile,
        kb_id=args.kb_id,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    if args.validate:
        profile_version = PROFILES[args.profile].version
        default_output_dir = os.path.join("data", "agentic_ready_data", args.profile, profile_version)
        if args.kb_id:
            safe_kb_id = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in args.kb_id)
            default_output_dir = os.path.join("data", "agentic_ready_data", "kbs", safe_kb_id, args.profile, profile_version)
        result = validate(
            args.output_dir
            or default_output_dir
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
