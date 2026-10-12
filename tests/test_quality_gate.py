from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

from scripts.quality_gate import (
    _run,
    compare_violations,
    parse_black_output,
    parse_isort_output,
    parse_pylint_output,
    update_baseline,
)


def test_run_echoes_child_output_before_child_exits(tmp_path: Path, monkeypatch) -> None:
    release_path = tmp_path / "release-child"
    child_marker = "CI_PROGRESS_SENTINEL"
    escaped_marker = "".join(f"\\x{ord(char):02x}" for char in child_marker)
    child_code = (
        "import sys, time; from pathlib import Path; "
        f"sys.stdout.write('{escaped_marker}'); sys.stdout.flush(); "
        "exec('while not Path(sys.argv[1]).exists(): time.sleep(0.01)')"
    )
    marker_seen = threading.Event()

    class RunnerOutput:
        def __init__(self) -> None:
            self.output = ""

        def write(self, text: str) -> int:
            self.output += text
            return len(text)

        def flush(self) -> None:
            if child_marker in self.output:
                marker_seen.set()

    monkeypatch.setattr(sys, "stdout", RunnerOutput())
    result = []
    runner = threading.Thread(
        target=lambda: result.append(
            _run([sys.executable, "-c", child_code, str(release_path)], tmp_path)
        )
    )
    runner.start()
    try:
        assert marker_seen.wait(timeout=10)
        assert runner.is_alive()
    finally:
        release_path.touch()
        runner.join(timeout=5)

    assert not runner.is_alive()
    assert result[0].returncode == 0
    assert result[0].stdout == child_marker


def test_run_captures_output_and_preserves_returncode_when_echo_is_disabled(
    tmp_path: Path, capfd
) -> None:
    first_stdout = repr(b"captured stdout\r")
    second_stdout = repr(b"\n\xc3")
    third_stdout = repr(b"\xa9")
    child_code = (
        "import sys,time; "
        f"sys.stdout.buffer.write({first_stdout}); sys.stdout.flush(); time.sleep(0.02); "
        f"sys.stdout.buffer.write({second_stdout}); sys.stdout.flush(); time.sleep(0.02); "
        f"sys.stdout.buffer.write({third_stdout}); sys.stdout.flush(); "
        "sys.stderr.write('captured stderr'); sys.stderr.flush(); sys.exit(7)"
    )
    result = _run(
        [
            sys.executable,
            "-c",
            child_code,
        ],
        tmp_path,
        echo_output=False,
    )

    assert result.returncode == 7
    assert result.stdout == "captured stdout\nécaptured stderr"
    runner_output = capfd.readouterr().out
    assert runner_output.count("captured stdout") == 1
    assert runner_output.count("captured stderr") == 1


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
