#!/usr/bin/env python3
"""Run Agentic RAG retrieval eval cases and print a report.

Usage:
    python scripts/run_agentic_retrieval_eval.py --help
    python scripts/run_agentic_retrieval_eval.py --cases eval/cases.jsonl --json
    python scripts/run_agentic_retrieval_eval.py --db-url-env DATABASE_URL --json
    python scripts/run_agentic_retrieval_eval.py --mode agentic --output-dir data/agentic_ready_data

Retrieval mode reads PostgreSQL via DATABASE_URL (or --db-url-env). DATA_DIR or
paths.data controls ready-data and other file artifacts; it does not select the database.
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path for direct script execution
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

if __name__ == "__main__":
    from ai_actuarial.agentic_rag.eval import main

    main()
