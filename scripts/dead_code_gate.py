#!/usr/bin/env python3
"""Layered dead-code checks with a normalized, shrink-only baseline."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True, order=True)
class Finding:
    path: str
    kind: str
    symbol: str
    confidence: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", self.path.replace("\\", "/"))

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.path, self.kind, self.symbol)


@dataclass(frozen=True)
class GateComparison:
    new: tuple[Finding, ...]
    stale: tuple[Finding, ...]
    high_confidence: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return not (self.new or self.stale or self.high_confidence)


@dataclass(frozen=True)
class ReachabilityConfig:
    source_roots: tuple[str, ...]
    production_entries: tuple[str, ...]
    script_entry_globs: tuple[str, ...]
    test_entry_globs: tuple[str, ...]
    dynamic_imports: tuple[str, ...]


@dataclass(frozen=True)
class _Module:
    name: str
    path: Path
    relative_path: str
    is_package: bool


KNIP_KINDS = {
    "files": "unused_file",
    "exports": "unused_export",
    "types": "unused_type",
    "enumMembers": "unused_enum_member",
    "namespaceMembers": "unused_namespace_member",
    "nsExports": "unused_namespace_export",
    "nsTypes": "unused_namespace_type",
    "duplicates": "duplicate_export",
}
VULTURE_LINE = re.compile(r"^(.*?):(\d+): (.*?) \((\d+)% confidence\)$")


def compare_findings(
    current: Iterable[Finding],
    baseline: Iterable[Finding],
    *,
    reject_confidence: int = 100,
) -> GateComparison:
    current_by_id = {finding.identity: finding for finding in current}
    baseline_by_id = {finding.identity: finding for finding in baseline}
    new = tuple(sorted(current_by_id[key] for key in current_by_id.keys() - baseline_by_id.keys()))
    stale = tuple(
        sorted(baseline_by_id[key] for key in baseline_by_id.keys() - current_by_id.keys())
    )
    high_confidence = tuple(
        sorted(
            finding for finding in current_by_id.values() if finding.confidence >= reject_confidence
        )
    )
    return GateComparison(new=new, stale=stale, high_confidence=high_confidence)


def parse_knip_report(raw: str) -> list[Finding]:
    data = json.loads(raw)
    findings: set[Finding] = set()
    for issue in data.get("issues", []):
        path = str(issue.get("file") or "")
        for raw_kind, normalized_kind in KNIP_KINDS.items():
            for item in issue.get(raw_kind, []):
                if raw_kind == "duplicates":
                    names = sorted(str(member.get("name") or "") for member in item)
                    findings.add(Finding(path, normalized_kind, " = ".join(names)))
                    continue
                name = str(item.get("name") or path)
                findings.add(Finding(path, normalized_kind, name))
    return sorted(findings)


def parse_vulture_output(raw: str) -> list[Finding]:
    findings: set[Finding] = set()
    for line in raw.splitlines():
        match = VULTURE_LINE.match(line.strip())
        if not match:
            continue
        path, _line_number, message, confidence_text = match.groups()
        quoted = re.search(r"'([^']+)'", message)
        if quoted:
            symbol = quoted.group(1)
            kind = message[: quoted.start()].strip()
        else:
            kind = "unreachable code" if message.startswith("unreachable code") else message
            symbol = message.removeprefix(kind).strip() or message
        findings.add(Finding(path, kind, symbol, int(confidence_text)))
    return sorted(findings)


def _module_name(relative_path: str) -> tuple[str, bool]:
    path = Path(relative_path)
    parts = list(path.with_suffix("").parts)
    is_package = bool(parts and parts[-1] == "__init__")
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _discover_modules(root: Path, config: ReachabilityConfig, mode: str) -> dict[str, _Module]:
    paths: set[Path] = set()
    for source_root in config.source_roots:
        directory = root / source_root
        if directory.exists():
            paths.update(directory.rglob("*.py"))
    if mode == "development":
        for pattern in config.test_entry_globs:
            paths.update(path for path in root.glob(pattern) if path.is_file())

    modules: dict[str, _Module] = {}
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        name, is_package = _module_name(relative)
        if name:
            modules[name] = _Module(name, path, relative, is_package)
    return modules


def _resolve_import_from(module: _Module, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    package_parts = module.name.split(".") if module.is_package else module.name.split(".")[:-1]
    ascend = node.level - 1
    if ascend > len(package_parts):
        return ""
    base = package_parts[: len(package_parts) - ascend]
    if node.module:
        base.extend(node.module.split("."))
    return ".".join(base)


def _module_edges(module: _Module, known: set[str]) -> tuple[set[str], set[str]]:
    try:
        tree = ast.parse(module.path.read_text(encoding="utf-8"), filename=module.relative_path)
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"Cannot analyze {module.relative_path}: {exc}") from exc

    edges: set[str] = set()
    dynamic: set[str] = set()

    def add(candidate: str) -> None:
        if candidate in known:
            edges.add(candidate)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import_from(module, node)
            add(base)
            for alias in node.names:
                if alias.name != "*":
                    add(f"{base}.{alias.name}" if base else alias.name)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            target = node.args[0].value
            if not isinstance(target, str):
                continue
            function_name = ""
            if isinstance(node.func, ast.Name):
                function_name = node.func.id
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                function_name = f"{node.func.value.id}.{node.func.attr}"
            if function_name in {"import_module", "importlib.import_module", "__import__"}:
                if target in known:
                    dynamic.add(target)
    return edges, dynamic


def _with_parent_packages(module_names: Iterable[str], known: set[str]) -> set[str]:
    expanded: set[str] = set()
    for module_name in module_names:
        parts = module_name.split(".")
        for index in range(1, len(parts) + 1):
            candidate = ".".join(parts[:index])
            if candidate in known:
                expanded.add(candidate)
    return expanded


def collect_python_module_findings(
    root: Path,
    config: ReachabilityConfig,
    mode: str = "production",
) -> list[Finding]:
    if mode not in {"production", "development"}:
        raise ValueError(f"Unsupported reachability mode: {mode}")
    modules = _discover_modules(root, config, mode)
    known = set(modules)
    graph: dict[str, set[str]] = {}
    dynamic_by_source: dict[str, set[str]] = {}
    detected_dynamic: set[str] = set()
    for name, module in modules.items():
        graph[name], module_dynamic = _module_edges(module, known)
        dynamic_by_source[name] = module_dynamic
        detected_dynamic.update(module_dynamic)

    approved_dynamic = set(config.dynamic_imports)
    unapproved = detected_dynamic - approved_dynamic
    if unapproved:
        raise ValueError("Unapproved dynamic import(s): " + ", ".join(sorted(unapproved)))
    stale_dynamic = approved_dynamic - detected_dynamic
    if stale_dynamic:
        raise ValueError("Stale dynamic import allowlist: " + ", ".join(sorted(stale_dynamic)))
    for source, edges in graph.items():
        edges.update(dynamic_by_source[source] & approved_dynamic)

    entries = set(config.production_entries)
    for pattern in config.script_entry_globs:
        for path in root.glob(pattern):
            if path.is_file():
                name, _is_package = _module_name(path.relative_to(root).as_posix())
                entries.add(name)
    if mode == "development":
        for pattern in config.test_entry_globs:
            for path in root.glob(pattern):
                if path.is_file():
                    name, _is_package = _module_name(path.relative_to(root).as_posix())
                    entries.add(name)

    missing_entries = entries - known
    if missing_entries:
        raise ValueError("Missing Python entry module(s): " + ", ".join(sorted(missing_entries)))

    reachable = _with_parent_packages(entries, known)
    pending = list(reachable)
    while pending:
        current = pending.pop()
        for target in _with_parent_packages(graph.get(current, ()), known):
            if target not in reachable:
                reachable.add(target)
                pending.append(target)

    source_prefixes = tuple(f"{root_name.rstrip('/')}/" for root_name in config.source_roots)
    findings = [
        Finding(module.relative_path, "unused_module", name)
        for name, module in modules.items()
        if module.relative_path.startswith(source_prefixes) and name not in reachable
    ]
    return sorted(findings)


def _load_project_config(root: Path) -> tuple[ReachabilityConfig, dict[str, object]]:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    tool = data.get("tool", {})
    dead_code = tool.get("dead_code", {})
    dynamic_entries = dead_code.get("dynamic_imports", [])
    dynamic_modules: list[str] = []
    for entry in dynamic_entries:
        module = str(entry.get("module") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        if not module or not reason:
            raise ValueError("Every tool.dead_code.dynamic_imports entry needs module and reason")
        dynamic_modules.append(module)
    reachability = ReachabilityConfig(
        source_roots=tuple(dead_code.get("source_roots", ())),
        production_entries=tuple(dead_code.get("production_entries", ())),
        script_entry_globs=tuple(dead_code.get("script_entry_globs", ())),
        test_entry_globs=tuple(dead_code.get("test_entry_globs", ())),
        dynamic_imports=tuple(dynamic_modules),
    )
    return reachability, tool.get("vulture", {})


def _source_for_module(root: Path, module_name: str) -> Path | None:
    base = root.joinpath(*module_name.split("."))
    module_file = base.with_suffix(".py")
    if module_file.is_file():
        return module_file
    package_file = base / "__init__.py"
    return package_file if package_file.is_file() else None


def _top_level_symbols(tree: ast.Module) -> dict[str, ast.AST]:
    symbols: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    symbols[target.id] = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                symbols[alias.asname or alias.name.split(".")[0]] = node
    return symbols


def validate_whitelist(root: Path, whitelist_path: Path) -> None:
    source = whitelist_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=whitelist_path.as_posix())
    except SyntaxError as exc:
        raise ValueError(f"Invalid Vulture whitelist syntax: {exc}") from exc

    imported: dict[str, ast.AST] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        module_path = _source_for_module(root, node.module)
        if module_path is None:
            raise ValueError(f"Stale whitelist module: {node.module}")
        target_tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        available = _top_level_symbols(target_tree)
        for alias in node.names:
            if alias.name not in available:
                raise ValueError(f"Stale whitelist import: {node.module}.{alias.name}")
            imported[alias.asname or alias.name] = available[alias.name]

    source_lines = source.splitlines()
    referenced: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Expr) or isinstance(node.value, ast.Constant):
            continue
        line = source_lines[node.lineno - 1]
        if "# reason:" not in line:
            raise ValueError(f"Whitelist reference on line {node.lineno} needs an inline reason")
        if isinstance(node.value, ast.Name):
            if node.value.id not in imported:
                raise ValueError(f"Unknown whitelist reference: {node.value.id}")
            referenced.add(node.value.id)
        elif isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name):
            owner_name = node.value.value.id
            owner = imported.get(owner_name)
            if not isinstance(owner, ast.ClassDef):
                raise ValueError(f"Unknown whitelist owner: {owner_name}")
            members = _top_level_symbols(ast.Module(body=owner.body, type_ignores=[]))
            if node.value.attr not in members:
                raise ValueError(f"Stale whitelist member: {owner_name}.{node.value.attr}")
            referenced.add(owner_name)
        else:
            raise ValueError(f"Unsupported whitelist reference on line {node.lineno}")

    unreferenced = sorted(imported.keys() - referenced)
    if unreferenced:
        raise ValueError("Whitelist imports need reviewed references: " + ", ".join(unreferenced))


def _json_line(raw: str, tool_name: str) -> str:
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return line
    raise RuntimeError(f"{tool_name} did not produce a JSON report:\n{raw}")


def _run(command: Sequence[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _run_knip(root: Path, gate: str) -> tuple[list[Finding], str]:
    binary = root / "node_modules/knip/bin/knip.js"
    if not binary.exists():
        raise RuntimeError("Knip is not installed; run `npm ci` first")
    includes = (
        "files"
        if gate == "typescript-files"
        else ("exports,types,enumMembers,namespaceMembers,nsExports,nsTypes,duplicates")
    )
    result = _run(
        [
            "node",
            str(binary),
            "--config",
            "knip.json",
            "--production",
            "--include",
            includes,
            "--reporter",
            "json",
        ],
        root,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"Knip failed with exit code {result.returncode}:\n{result.stdout}")
    return parse_knip_report(_json_line(result.stdout, "Knip")), result.stdout


def _run_eslint(root: Path) -> tuple[list[Finding], str]:
    binary = root / "node_modules/eslint/bin/eslint.js"
    if not binary.exists():
        raise RuntimeError("ESLint is not installed; run `npm ci` first")
    result = _run(
        ["node", str(binary), "client/src", "--format", "json"],
        root,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"ESLint failed with exit code {result.returncode}:\n{result.stdout}")
    findings: list[Finding] = []
    for file_result in json.loads(result.stdout or "[]"):
        path = Path(file_result["filePath"]).resolve().relative_to(root.resolve()).as_posix()
        for message in file_result.get("messages", []):
            if int(message.get("severity", 0)) < 2:
                continue
            rule = str(message.get("ruleId") or "parse-error")
            findings.append(Finding(path, f"eslint:{rule}", str(message.get("message") or rule)))
    return sorted(set(findings)), result.stdout


def _run_vulture(root: Path) -> tuple[list[Finding], str]:
    result = _run([sys.executable, "-m", "vulture"], root)
    if result.returncode not in {0, 3}:
        raise RuntimeError(f"Vulture failed with exit code {result.returncode}:\n{result.stdout}")
    return parse_vulture_output(result.stdout), result.stdout


def _load_baseline(root: Path, gate: str) -> list[Finding]:
    data = json.loads((root / "dead-code-baseline.json").read_text(encoding="utf-8"))
    return [
        Finding(
            path=item["path"],
            kind=item["kind"],
            symbol=item["symbol"],
            confidence=int(item.get("confidence", 0)),
        )
        for item in data.get("gates", {}).get(gate, [])
    ]


def update_baseline(baseline_path: Path, gate: str, current: Sequence[Finding]) -> None:
    """Remove resolved findings from a gate without allowing baseline growth."""
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    gate_items = data.get("gates", {}).get(gate)
    if gate_items is None:
        raise ValueError(f"Unknown baseline gate: {gate}")

    existing_by_id = {
        (item["path"].replace("\\", "/"), item["kind"], item["symbol"]): item for item in gate_items
    }
    current_by_id = {finding.identity: finding for finding in current}
    additions = sorted(current_by_id.keys() - existing_by_id.keys())
    if additions:
        formatted = ", ".join(" | ".join(identity) for identity in additions)
        raise ValueError(f"Baseline update would grow {gate}: {formatted}")

    if gate == "python-symbols":
        certain = sorted(finding.identity for finding in current if finding.confidence >= 100)
        if certain:
            formatted = ", ".join(" | ".join(identity) for identity in certain)
            raise ValueError(f"Baseline cannot contain 100% confidence findings: {formatted}")

    retained = []
    for item in gate_items:
        identity = (item["path"].replace("\\", "/"), item["kind"], item["symbol"])
        finding = current_by_id.get(identity)
        if finding is None:
            continue
        retained_item = dict(item)
        retained_item["path"] = identity[0]
        retained_item["confidence"] = finding.confidence
        retained.append(retained_item)

    data["gates"][gate] = retained
    baseline_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_report(
    report_dir: Path,
    gate: str,
    findings: Sequence[Finding],
    comparison: GateComparison,
    hard_findings: Sequence[Finding],
    raw_output: str,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "gate": gate,
        "ok": comparison.ok and not hard_findings,
        "findings": [asdict(finding) for finding in findings],
        "new": [asdict(finding) for finding in comparison.new],
        "stale": [asdict(finding) for finding in comparison.stale],
        "high_confidence": [asdict(finding) for finding in comparison.high_confidence],
        "hard_findings": [asdict(finding) for finding in hard_findings],
    }
    (report_dir / f"{gate}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    lines = [f"{gate}: {'PASS' if payload['ok'] else 'FAIL'}", f"findings: {len(findings)}"]
    for label, values in (
        ("new", comparison.new),
        ("stale baseline", comparison.stale),
        ("100% confidence", comparison.high_confidence),
        ("direct failures", hard_findings),
    ):
        if values:
            lines.append(f"{label}:")
            lines.extend(f"  {item.path} | {item.kind} | {item.symbol}" for item in values)
    (report_dir / f"{gate}.txt").write_text(
        "\n".join(lines) + "\n\n" + raw_output, encoding="utf-8"
    )


def _run_gate(
    root: Path,
    gate: str,
    mode: str,
    report_dir: Path,
    *,
    update: bool = False,
) -> bool:
    hard_findings: list[Finding] = []
    raw_output = ""
    if gate.startswith("typescript-"):
        findings, raw_output = _run_knip(root, gate)
        if gate == "typescript-symbols":
            hard_findings, eslint_raw = _run_eslint(root)
            raw_output += "\nESLint:\n" + eslint_raw
    elif gate == "python-files":
        config, _vulture = _load_project_config(root)
        findings = collect_python_module_findings(root, config, mode=mode)
        raw_output = "\n".join(
            f"{finding.path}: {finding.kind} '{finding.symbol}'" for finding in findings
        )
    elif gate == "python-symbols":
        _reachability, vulture_config = _load_project_config(root)
        whitelist_paths = [
            root / str(path)
            for path in vulture_config.get("paths", [])
            if str(path).endswith("whitelist.py")
        ]
        if len(whitelist_paths) != 1:
            raise ValueError("tool.vulture.paths must contain exactly one whitelist.py")
        validate_whitelist(root, whitelist_paths[0])
        findings, raw_output = _run_vulture(root)
    else:
        raise ValueError(f"Unknown gate: {gate}")

    baseline = _load_baseline(root, gate)
    comparison = compare_findings(
        findings,
        baseline,
        reject_confidence=100 if gate == "python-symbols" else 101,
    )
    if update and not hard_findings:
        update_baseline(root / "dead-code-baseline.json", gate, findings)
        baseline = _load_baseline(root, gate)
        comparison = compare_findings(
            findings,
            baseline,
            reject_confidence=100 if gate == "python-symbols" else 101,
        )
    _write_report(report_dir, gate, findings, comparison, hard_findings, raw_output)
    ok = comparison.ok and not hard_findings
    print(f"{gate}: {'PASS' if ok else 'FAIL'} ({len(findings)} baseline findings)")
    if not ok:
        for label, values in (
            ("new", comparison.new),
            ("stale baseline", comparison.stale),
            ("100% confidence", comparison.high_confidence),
            ("direct failures", hard_findings),
        ):
            for finding in values:
                print(f"  {label}: {finding.path} | {finding.kind} | {finding.symbol}")
    return ok


GATE_GROUPS = {
    "typescript-files": ("typescript-files",),
    "python-files": ("python-files",),
    "files": ("typescript-files", "python-files"),
    "typescript-symbols": ("typescript-symbols",),
    "python-symbols": ("python-symbols",),
    "symbols": ("typescript-symbols", "python-symbols"),
    "all": ("typescript-files", "python-files", "typescript-symbols", "python-symbols"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=GATE_GROUPS)
    parser.add_argument("--mode", choices=("production", "development"), default="production")
    parser.add_argument("--report-dir", default="reports/dead-code")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="remove resolved findings from the baseline; additions are always rejected",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    report_dir = root / args.report_dir
    try:
        results = [
            _run_gate(
                root,
                gate,
                args.mode,
                report_dir,
                update=args.update_baseline,
            )
            for gate in GATE_GROUPS[args.gate]
        ]
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"dead-code gate error: {exc}", file=sys.stderr)
        return 2
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
