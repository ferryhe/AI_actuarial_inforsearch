from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_actuarial.postgres import (  # noqa: E402
    PostgresConnection,
    resolve_data_root,
    resolve_database_config,
    run_postgres_dump,
)
from config.yaml_config import load_database_config  # noqa: E402

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


def ensure_backup(database_url, schema: str, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    run_postgres_dump(database_url, backup_path, schema=schema)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove page number lines from markdown_content in catalog_items."
    )
    parser.add_argument(
        "--database-url-env",
        default="",
        help="Environment variable containing the PostgreSQL URL (default: configured URL variable)",
    )
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
        help="Optional native PostgreSQL custom-format backup path.",
    )
    args = parser.parse_args()

    database_settings = load_database_config()
    if args.database_url_env:
        database_settings = {**database_settings, "url_env": args.database_url_env}
    database = resolve_database_config({"database": database_settings})
    conn = PostgresConnection(database)
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
                changed_rows.append(
                    (
                        row["file_url"],
                        row["markdown_source"] or "",
                        result.markdown,
                        result.removed_lines,
                    )
                )

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
            backup_path = (
                resolve_data_root() / "backups" / f"catalog_before_page_cleanup_{stamp}.dump"
            )
        schema = str(conn.execute("SELECT current_schema()").fetchone()[0])
        ensure_backup(database, schema, backup_path)
        print(f"\nPostgreSQL backup created: {backup_path}")

        conn.execute("BEGIN")
        try:
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
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        print(f"Updated rows: {len(changed_rows)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
