from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality_gate import (
    compare_violations,
    parse_black_output,
    parse_isort_output,
    parse_pylint_output,
    update_baseline,
)


def test_formatter_output_is_normalized_to_repository_paths(tmp_path: Path) -> None:
    python_file = tmp_path / "pkg" / "module.py"
    black_output = "would reformat pkg\\module.py\n"
    isort_output = f"ERROR: {python_file} Imports are incorrectly sorted and/or formatted.\n"

    assert parse_black_output(black_output, tmp_path) == ["pkg/module.py"]
    assert parse_isort_output(isort_output, tmp_path) == ["pkg/module.py"]


def test_pylint_output_uses_path_message_and_symbol_identity(tmp_path: Path) -> None:
    output = json.dumps(
        [
            {
                "path": str(tmp_path / "pkg" / "module.py"),
                "message-id": "E1101",
                "module": "pkg.module",
                "obj": "Widget.render",
                "symbol": "no-member",
                "message": "Instance has no member",
            }
        ]
    )

    assert parse_pylint_output(output, tmp_path) == [
        "pkg/module.py | E1101 | Widget.render | Instance has no member"
    ]


def test_quality_baseline_is_exact_and_shrink_only(tmp_path: Path) -> None:
    baseline_path = tmp_path / "quality-gate-baseline.json"
    baseline_path.write_text(
        json.dumps({"version": 1, "tools": {"black": ["old.py"], "isort": [], "pylint": []}}),
        encoding="utf-8",
    )

    assert compare_violations([], ["old.py"]) == ([], ["old.py"])
    update_baseline(baseline_path, {"black": [], "isort": [], "pylint": []})
    assert json.loads(baseline_path.read_text(encoding="utf-8"))["tools"]["black"] == []

    with pytest.raises(ValueError, match="would grow black"):
        update_baseline(
            baseline_path,
            {"black": ["new.py"], "isort": [], "pylint": []},
        )
