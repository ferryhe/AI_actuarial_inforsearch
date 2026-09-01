#!/usr/bin/env python3
"""Run the repository's unified, non-mutating Python quality gate."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

SOURCE_PATHS = ("ai_actuarial", "scripts", "tests", "config")
BLACK_LINE = re.compile(r"^would reformat (.+)$")
ISORT_LINE = re.compile(r"^ERROR: (.+?) Imports are incorrectly sorted and/or formatted\.$")


def _normalize_path(raw_path: str, root: Path) -> str:
    path = Path(raw_path.strip())
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return raw_path.strip().replace("\\", "/")


def parse_black_output(output: str, root: Path) -> list[str]:
    return sorted(
        {
            _normalize_path(match.group(1), root)
            for line in output.splitlines()
            if (match := BLACK_LINE.match(line.strip()))
        }
    )


def parse_isort_output(output: str, root: Path) -> list[str]:
    return sorted(
        {
            _normalize_path(match.group(1), root)
            for line in output.splitlines()
            if (match := ISORT_LINE.match(line.strip()))
        }
    )


def parse_pylint_output(output: str, root: Path) -> list[str]:
    messages = json.loads(output or "[]")
    return sorted(
        {
            " | ".join(
                (
                    _normalize_path(str(message["path"]), root),
                    str(message["message-id"]),
                    str(message.get("obj") or message.get("module") or "<module>"),
                    str(message["message"]),
                )
            )
            for message in messages
        }
    )


def compare_violations(
    current: Sequence[str], baseline: Sequence[str]
) -> tuple[list[str], list[str]]:
    current_set = set(current)
    baseline_set = set(baseline)
    return sorted(current_set - baseline_set), sorted(baseline_set - current_set)


def update_baseline(baseline_path: Path, current: dict[str, Sequence[str]]) -> None:
    """Remove resolved formatting violations without accepting new ones."""
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    tools = data.get("tools", {})
    for tool, violations in current.items():
        if tool not in tools:
            raise ValueError(f"Unknown quality baseline tool: {tool}")
        new, _stale = compare_violations(violations, tools[tool])
        if new:
            raise ValueError(f"Quality baseline update would grow {tool}: {', '.join(new)}")
    for tool, violations in current.items():
        tools[tool] = sorted(set(violations))
    baseline_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _run(
    command: Sequence[str], root: Path, *, echo_output: bool = True
) -> subprocess.CompletedProcess[str]:
    print(f"+ {' '.join(command)}", flush=True)
    result = subprocess.run(
        command,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if echo_output and result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    return result


def _format_scan(
    root: Path,
    module: str,
    check_arg: str,
    parser: Callable[[str, Path], list[str]],
) -> tuple[list[str], str]:
    result = _run(
        [sys.executable, "-m", module, check_arg, *SOURCE_PATHS],
        root,
        echo_output=False,
    )
    if result.returncode not in {0, 1}:
        print(result.stdout, file=sys.stderr)
        raise RuntimeError(f"{module} failed with exit code {result.returncode}")
    return parser(result.stdout, root), result.stdout


def _pylint_scan(root: Path) -> tuple[list[str], str]:
    result = _run(
        [
            sys.executable,
            "-m",
            "pylint",
            "--errors-only",
            "--disable=import-error",
            "--output-format=json",
            *SOURCE_PATHS,
        ],
        root,
        echo_output=False,
    )
    try:
        violations = parse_pylint_output(result.stdout, root)
    except json.JSONDecodeError as exc:
        raise RuntimeError("pylint did not produce valid JSON") from exc
    return violations, result.stdout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", default="reports/quality-gate")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="remove resolved formatting violations; additions are always rejected",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    report_dir = root / args.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)

    pytest_result = _run([sys.executable, "-m", "pytest", "-q"], root)
    try:
        black_violations, black_output = _format_scan(root, "black", "--check", parse_black_output)
        isort_violations, isort_output = _format_scan(
            root, "isort", "--check-only", parse_isort_output
        )
    except RuntimeError as exc:
        print(f"quality gate error: {exc}", file=sys.stderr)
        return 2
    try:
        pylint_violations, pylint_output = _pylint_scan(root)
    except RuntimeError as exc:
        print(f"quality gate error: {exc}", file=sys.stderr)
        return 2

    baseline_path = root / "quality-gate-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["tools"]
    current = {
        "black": black_violations,
        "isort": isort_violations,
        "pylint": pylint_violations,
    }
    comparisons = {
        tool: compare_violations(violations, baseline[tool]) for tool, violations in current.items()
    }

    direct_failures = []
    if pytest_result.returncode:
        direct_failures.append("pytest")
    if args.update_baseline and not direct_failures:
        try:
            update_baseline(baseline_path, current)
        except ValueError as exc:
            print(f"quality gate error: {exc}", file=sys.stderr)
            return 2
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["tools"]
        comparisons = {
            tool: compare_violations(violations, baseline[tool])
            for tool, violations in current.items()
        }

    ok = not direct_failures and all(not new and not stale for new, stale in comparisons.values())
    payload = {
        "ok": ok,
        "direct_failures": direct_failures,
        "tools": {
            tool: {"violations": current[tool], "new": new, "stale": stale}
            for tool, (new, stale) in comparisons.items()
        },
    }
    (report_dir / "quality-gate.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (report_dir / "quality-gate.txt").write_text(
        "\n".join(
            [
                f"quality gate: {'PASS' if ok else 'FAIL'}",
                f"direct failures: {', '.join(direct_failures) or 'none'}",
                *[
                    f"{tool}: {len(current[tool])} baseline violations, "
                    f"{len(new)} new, {len(stale)} stale"
                    for tool, (new, stale) in comparisons.items()
                ],
                "",
                "Black output:",
                black_output,
                "Isort output:",
                isort_output,
                "Pylint output:",
                pylint_output,
                "Pytest output:",
                pytest_result.stdout,
            ]
        ),
        encoding="utf-8",
    )
    print(f"quality gate: {'PASS' if ok else 'FAIL'}")
    for tool, (new, stale) in comparisons.items():
        for path in new:
            print(f"  new {tool} violation: {path}")
        for path in stale:
            print(f"  stale {tool} baseline: {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
