"""Reconcile KBs that predate the persisted chunk-binding table.

The command is read-only by default.  Pass ``--apply`` to persist the
profile correction, bindings, and audit events reported by the dry run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_actuarial.rag.kb_index import reconcile_legacy_kb_bindings
from ai_actuarial.storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default="data/index.db",
        help="Path to the SQLite database (default: data/index.db)",
    )
    parser.add_argument(
        "--kb-id",
        action="append",
        dest="kb_ids",
        help="Only reconcile this KB; repeat the option for multiple KBs",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the planned reconciliation; without this flag the command is dry-run",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request the default read-only mode",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.apply and args.dry_run:
        raise SystemExit("--apply and --dry-run cannot be used together")
    db_path = Path(args.db)
    storage = Storage(str(db_path))
    try:
        report = reconcile_legacy_kb_bindings(
            storage,
            args.kb_ids,
            dry_run=not args.apply,
        )
    finally:
        storage.close()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
