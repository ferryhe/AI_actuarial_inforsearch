from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from ai_actuarial.catalog import build_catalog, write_catalog_md
from ai_actuarial.storage import Storage


def _db_count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.execute("SELECT COUNT(*) FROM files")
    (count,) = cur.fetchone()
    conn.close()
    return count


def _current_count(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return len(data)


def main() -> int:
    db_path = os.getenv("CATALOG_DB", "data/index.db")
    out_json = Path(os.getenv("CATALOG_JSON", "data/catalog.json"))
    out_md = Path(os.getenv("CATALOG_MD", "data/catalog.md"))
    batch = int(os.getenv("CATALOG_BATCH", "200"))
    site_filter = os.getenv("CATALOG_SITE")
    ai_only = os.getenv("CATALOG_AI_ONLY", "0") == "1"

    total = _db_count(db_path)
    done = _current_count(out_json)

    storage = Storage(db_path)
    offset = done
    while offset < total:
        items = build_catalog(
            storage,
            site_filter=site_filter,
            limit=batch,
            ai_only=ai_only,
            offset=offset,
        )
        if not items:
            break

        if out_json.exists():
            with open(out_json, "r", encoding="utf-8") as f:
                existing = json.load(f)
        else:
            existing = []
        existing.extend([item.__dict__ for item in items])
        out_json.parent.mkdir(parents=True, exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        write_catalog_md(out_md, items, append=out_md.exists())

        offset += len(items)
        print(f"progress: {offset}/{total}")

        if len(items) < batch:
            break

    storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
