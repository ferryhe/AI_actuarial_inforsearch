from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


LINE_PATTERNS = [
    re.compile(r"^\s*#{1,6}\s*page\s+\d+(?:\s+of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*page\s+\d+(?:\s+of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*第\s*\d+\s*页(?:\s*/\s*共\s*\d+\s*页)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$", re.IGNORECASE),
]


@dataclass
class CleanResult:
    changed: bool
    removed_lines: int
    markdown: str


def clean_markdown(text: str) -> CleanResult:
    if text is None:
        return CleanResult(changed=False, removed_lines=0, markdown="")

    original = text
    lines = text.splitlines()
    kept: list[str] = []
    removed = 0

    for line in lines:
        if any(pat.match(line) for pat in LINE_PATTERNS):
            removed += 1
            continue
        kept.append(line.rstrip())

    # Normalize blank line runs after removing page marker lines.
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if original.endswith("\n") and cleaned:
        cleaned += "\n"

    return CleanResult(changed=(cleaned != original), removed_lines=removed, markdown=cleaned)


def ensure_backup(conn: sqlite3.Connection, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_conn = sqlite3.connect(str(backup_path))
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove page number lines from markdown_content in catalog_items.")
    parser.add_argument("--db", default="data/index.db", help="SQLite database path (default: data/index.db)")
    parser.add_argument(
        "--source-like",
        default="%",
        help="SQL LIKE filter for markdown_source (default: %% = all sources)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply updates. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--backup",
        default="",
        help="Optional backup path. Default when --apply: data/backups/index_before_md_page_cleanup_<timestamp>.db",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT file_url, markdown_source, markdown_content
            FROM catalog_items
            WHERE markdown_content IS NOT NULL
              AND TRIM(markdown_content) != ''
              AND COALESCE(markdown_source, '') LIKE ?
            """,
            (args.source_like,),
        ).fetchall()

        candidates = 0
        changed_rows: list[tuple[str, str, str, int]] = []
        removed_lines_total = 0

        for row in rows:
            result = clean_markdown(row["markdown_content"])
            if result.changed and result.removed_lines > 0:
                candidates += 1
                removed_lines_total += result.removed_lines
                changed_rows.append((row["file_url"], row["markdown_source"] or "", result.markdown, result.removed_lines))

        print(f"Scanned rows: {len(rows)}")
        print(f"Rows that would change: {candidates}")
        print(f"Page-marker lines to remove: {removed_lines_total}")

        if not changed_rows:
            print("No updates needed.")
            return 0

        preview_n = min(8, len(changed_rows))
        print("\nPreview:")
        for file_url, source, _, removed_lines in changed_rows[:preview_n]:
            print(f"- source={source or '-'} removed_lines={removed_lines} url={file_url}")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to persist changes.")
            return 0

        if args.backup:
            backup_path = Path(args.backup)
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = Path("data/backups") / f"index_before_md_page_cleanup_{stamp}.db"
        ensure_backup(conn, backup_path)
        print(f"\nBackup created: {backup_path}")

        with conn:
            for file_url, _source, cleaned, _removed_lines in changed_rows:
                conn.execute(
                    """
                    UPDATE catalog_items
                    SET markdown_content = ?,
                        markdown_updated_at = CURRENT_TIMESTAMP
                    WHERE file_url = ?
                    """,
                    (cleaned, file_url),
                )

        print(f"Updated rows: {len(changed_rows)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
