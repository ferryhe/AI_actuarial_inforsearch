#!/usr/bin/env python3
"""Run Agentic RAG retrieval eval cases and print a report.

Usage:
    python3 scripts/run_agentic_retrieval_eval.py
    python3 scripts/run_agentic_retrieval_eval.py --db data/index.db
    python3 scripts/run_agentic_retrieval_eval.py --cases eval/cases.jsonl --json
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
