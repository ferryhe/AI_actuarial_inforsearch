from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dead_code_gate import (
    Finding,
    ReachabilityConfig,
    collect_python_module_findings,
    compare_findings,
    parse_knip_report,
    parse_vulture_output,
    update_baseline,
    validate_whitelist,
)


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture_config(*, dynamic_imports: tuple[str, ...] = ()) -> ReachabilityConfig:
    return ReachabilityConfig(
        source_roots=("ai_actuarial", "scripts"),
        production_entries=("ai_actuarial.__main__",),
        script_entry_globs=("scripts/*.py",),
        test_entry_globs=("tests/**/*.py",),
        dynamic_imports=dynamic_imports,
    )


def test_python_production_scan_does_not_let_tests_keep_source_alive(tmp_path: Path) -> None:
    _write(tmp_path / "ai_actuarial/__init__.py")
    _write(tmp_path / "ai_actuarial/__main__.py", "from .live import run\nrun()\n")
    _write(tmp_path / "ai_actuarial/live.py", "from .leaf import answer\nrun = answer\n")
    _write(tmp_path / "ai_actuarial/leaf.py", "def answer():\n    return 42\n")
    _write(tmp_path / "ai_actuarial/test_only.py", "VALUE = 1\n")
    _write(tmp_path / "tests/test_live.py", "from ai_actuarial import test_only\n")
    _write(tmp_path / "scripts/tool.py", "from ai_actuarial.live import run\n")

    production = collect_python_module_findings(tmp_path, _fixture_config(), mode="production")
    development = collect_python_module_findings(tmp_path, _fixture_config(), mode="development")

    assert [finding.path for finding in production] == ["ai_actuarial/test_only.py"]
    assert development == []


def test_python_scan_reports_module_after_last_caller_is_removed(tmp_path: Path) -> None:
    _write(tmp_path / "ai_actuarial/__init__.py")
    entry = tmp_path / "ai_actuarial/__main__.py"
    _write(entry, "from .helper import value\nprint(value)\n")
    _write(tmp_path / "ai_actuarial/helper.py", "value = 1\n")

    assert collect_python_module_findings(tmp_path, _fixture_config()) == []

    _write(entry, "print('no helper')\n")
    findings = collect_python_module_findings(tmp_path, _fixture_config())

    assert [(finding.kind, finding.symbol) for finding in findings] == [
        ("unused_module", "ai_actuarial.helper")
    ]


def test_dynamic_repository_imports_require_reviewed_allowlist(tmp_path: Path) -> None:
    _write(tmp_path / "ai_actuarial/__init__.py")
    _write(
        tmp_path / "ai_actuarial/__main__.py",
        "import importlib\nimportlib.import_module('ai_actuarial.plugin')\n",
    )
    _write(tmp_path / "ai_actuarial/plugin.py", "PLUGIN = True\n")

    with pytest.raises(ValueError, match="Unapproved dynamic import.*ai_actuarial.plugin"):
        collect_python_module_findings(tmp_path, _fixture_config())

    assert (
        collect_python_module_findings(
            tmp_path,
            _fixture_config(dynamic_imports=("ai_actuarial.plugin",)),
        )
        == []
    )

    _write(tmp_path / "ai_actuarial/__main__.py", "from . import plugin\n")
    with pytest.raises(ValueError, match="Stale dynamic import allowlist"):
        collect_python_module_findings(
            tmp_path,
            _fixture_config(dynamic_imports=("ai_actuarial.plugin",)),
        )


def test_ratchet_rejects_new_stale_and_any_100_percent_findings() -> None:
    existing = Finding("pkg/legacy.py", "unused function", "legacy", confidence=60)
    new = Finding("pkg/new.py", "unused class", "NewThing", confidence=60)
    certain = Finding("pkg/live.py", "unused variable", "value", confidence=100)

    exact = compare_findings([existing], [existing])
    assert exact.ok

    growth = compare_findings([existing, new], [existing])
    assert not growth.ok
    assert growth.new == (new,)

    shrink_without_baseline_update = compare_findings([], [existing])
    assert not shrink_without_baseline_update.ok
    assert shrink_without_baseline_update.stale == (existing,)

    baseline_cannot_hide_certain = compare_findings([certain], [certain])
    assert not baseline_cannot_hide_certain.ok
    assert baseline_cannot_hide_certain.high_confidence == (certain,)


def test_knip_json_is_normalized_without_line_numbers() -> None:
    raw = json.dumps(
        {
            "issues": [
                {
                    "file": "client/src/orphan.ts",
                    "files": [{"name": "client/src/orphan.ts"}],
                    "exports": [{"name": "unusedExport", "line": 8, "col": 1}],
                    "types": [{"name": "UnusedType", "line": 12, "col": 1}],
                    "duplicates": [
                        [
                            {"name": "second", "line": 18, "col": 1},
                            {"name": "first", "line": 14, "col": 1},
                        ]
                    ],
                }
            ]
        }
    )

    findings = parse_knip_report(raw)

    assert findings == [
        Finding("client/src/orphan.ts", "duplicate_export", "first = second"),
        Finding("client/src/orphan.ts", "unused_export", "unusedExport"),
        Finding("client/src/orphan.ts", "unused_file", "client/src/orphan.ts"),
        Finding("client/src/orphan.ts", "unused_type", "UnusedType"),
    ]


def test_vulture_output_is_normalized_without_line_numbers() -> None:
    output = "\n".join(
        [
            "pkg\\module.py:8: unused function 'old' (60% confidence)",
            "pkg/module.py:20: unused variable 'certain' (100% confidence)",
        ]
    )

    assert parse_vulture_output(output) == [
        Finding("pkg/module.py", "unused function", "old", confidence=60),
        Finding("pkg/module.py", "unused variable", "certain", confidence=100),
    ]


def test_whitelist_references_must_have_reasons_and_resolve(tmp_path: Path) -> None:
    target = tmp_path / "pkg/hooks.py"
    whitelist = tmp_path / "config/dead_code_whitelist.py"
    _write(tmp_path / "pkg/__init__.py")
    _write(target, "def registered():\n    return True\n")
    _write(
        whitelist,
        "from pkg.hooks import registered\n\n" "registered  # reason: Framework registration.\n",
    )

    validate_whitelist(tmp_path, whitelist)

    _write(target, "def replacement():\n    return True\n")
    with pytest.raises(ValueError, match="Stale whitelist import.*registered"):
        validate_whitelist(tmp_path, whitelist)

    _write(whitelist, "from pkg.hooks import replacement\n\nreplacement\n")
    with pytest.raises(ValueError, match="needs an inline reason"):
        validate_whitelist(tmp_path, whitelist)

    _write(whitelist, "from pkg.hooks import replacement\n")
    with pytest.raises(ValueError, match="imports need reviewed references.*replacement"):
        validate_whitelist(tmp_path, whitelist)


def test_baseline_update_can_only_remove_and_preserves_classification(tmp_path: Path) -> None:
    baseline_path = tmp_path / "dead-code-baseline.json"
    existing = Finding("pkg/legacy.py", "unused function", "legacy", confidence=60)
    removed = Finding("pkg/removed.py", "unused class", "Removed", confidence=60)
    baseline_path.write_text(
        json.dumps(
            {
                "version": 1,
                "gates": {
                    "python-symbols": [
                        {
                            **existing.__dict__,
                            "classification": "remove",
                            "reason": "Reviewed cleanup candidate.",
                        },
                        {
                            **removed.__dict__,
                            "classification": "remove",
                            "reason": "Reviewed cleanup candidate.",
                        },
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    update_baseline(baseline_path, "python-symbols", [existing])
    updated = json.loads(baseline_path.read_text(encoding="utf-8"))

    assert updated["gates"]["python-symbols"] == [
        {
            **existing.__dict__,
            "classification": "remove",
            "reason": "Reviewed cleanup candidate.",
        }
    ]

    with pytest.raises(ValueError, match="would grow"):
        update_baseline(
            baseline_path,
            "python-symbols",
            [existing, Finding("pkg/new.py", "unused function", "new")],
        )
