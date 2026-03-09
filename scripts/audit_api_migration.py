from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


CLIENT_API_PATTERN = re.compile(r'["\'`](/api[^"\'`]*)["\'`]')
TEMPLATE_EXPR_PATTERN = re.compile(r"\$\{[^}]+\}")
SERVER_PARAM_PATTERN = re.compile(r"<(?:[^:>]+:)?([^>]+)>")
TRAILING_QUERY_PLACEHOLDER_PATTERN = re.compile(r"(?<!/)\{param\}$")


def normalize_client_path(path: str) -> str:
    path = path.split("?", 1)[0]
    path = TEMPLATE_EXPR_PATTERN.sub("{param}", path)
    path = TRAILING_QUERY_PLACEHOLDER_PATTERN.sub("", path)
    return path


def normalize_server_path(path: str) -> str:
    return SERVER_PARAM_PATTERN.sub("{param}", path)


def collect_client_paths(root: Path) -> dict[str, set[str]]:
    matches: dict[str, set[str]] = defaultdict(set)
    for file_path in root.rglob("*.[tj]s*"):
        text = file_path.read_text(encoding="utf-8")
        for match in CLIENT_API_PATTERN.findall(text):
            matches[normalize_client_path(match)].add(str(file_path.relative_to(root.parent)))
    return dict(sorted(matches.items()))


def collect_fastapi_paths() -> set[str]:
    from ai_actuarial.api.app import create_app

    app = create_app()
    return {normalize_server_path(path) for path in getattr(app.state, "native_paths", [])}


def collect_flask_paths() -> set[str]:
    from ai_actuarial.web.app import create_app as create_flask_app

    app = create_flask_app()
    return {
        normalize_server_path(rule.rule)
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api")
    }


def render_report(
    client_paths: dict[str, set[str]],
    fastapi_paths: set[str],
    flask_paths: set[str],
) -> str:
    lines: list[str] = []
    native = 0
    legacy = 0
    unknown = 0

    lines.append("# React API 迁移清单")
    lines.append("")
    lines.append("## 统计")
    lines.append("")
    lines.append(f"- React 检测到的 API 路径数: {len(client_paths)}")
    lines.append(f"- FastAPI 原生路径数: {len(fastapi_paths)}")
    lines.append(f"- Flask legacy API 路径数: {len(flask_paths)}")
    lines.append("")
    lines.append("## 逐项清单")
    lines.append("")
    lines.append("| 路径 | 当前状态 | 引用位置 |")
    lines.append("|---|---|---|")

    for path, refs in client_paths.items():
        if path in fastapi_paths:
            status = "FastAPI 原生"
            native += 1
        elif path in flask_paths:
            status = "Legacy Flask"
            legacy += 1
        else:
            status = "待确认"
            unknown += 1
        lines.append(f"| `{path}` | {status} | {', '.join(sorted(refs))} |")

    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- FastAPI 原生覆盖: {native}")
    lines.append(f"- Legacy Flask 回退: {legacy}")
    lines.append(f"- 待确认: {unknown}")
    lines.append("")
    lines.append("## 建议的下一批迁移")
    lines.append("")
    lines.append("- 先迁移读多写少、公共页面都会用到的接口，例如 `/api/stats`、`/api/files`、`/api/categories`。")
    lines.append("- 认证、任务调度、RAG、Chat 等高耦合模块继续暂时走 legacy Flask。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--client-root",
        default="client/src",
        help="Path to the React source tree",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional markdown output path",
    )
    args = parser.parse_args()

    client_root = Path(args.client_root)
    client_paths = collect_client_paths(client_root)
    fastapi_paths = collect_fastapi_paths()
    flask_paths = collect_flask_paths()
    report = render_report(client_paths, fastapi_paths, flask_paths)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
