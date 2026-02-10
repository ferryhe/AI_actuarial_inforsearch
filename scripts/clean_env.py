import argparse
import datetime as _dt
import os
import re
import secrets
from pathlib import Path


_ASSIGN_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")


def _parse_env_lines(lines: list[str]) -> tuple[dict[str, str], dict[str, int]]:
    """
    Parse KEY=VALUE pairs from .env-style lines.

    - Keeps the last occurrence for each key (last-wins).
    - Does not attempt to fully replicate any particular .env parser; the goal
      is deterministic cleanup, not perfect round-trip of exotic syntax.
    - Removes inline comments that are preceded by at least one whitespace:
        FOO=bar  # comment  -> value "bar"
    """
    values: dict[str, str] = {}
    counts: dict[str, int] = {}
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = _ASSIGN_RE.match(raw)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        # Strip unquoted inline comment markers (common .env convention).
        if val and not (val.startswith("'") or val.startswith('"')):
            # Split on " #", "\t#" etc; preserve "#" in URLs/tokens if adjacent.
            val = re.split(r"\s+#", val, maxsplit=1)[0]
        values[key] = val
        counts[key] = counts.get(key, 0) + 1
    return values, counts


def _needs_quotes(val: str) -> bool:
    if val == "":
        return False
    # Spaces, tabs, or leading/trailing whitespace are easiest to keep stable with quotes.
    if val != val.strip():
        return True
    if any(ch in val for ch in [" ", "\t", "#"]):
        return True
    return False


def _format_value(val: str) -> str:
    if not _needs_quotes(val):
        return val
    escaped = val.replace("\\", "\\\\").replace('"', '\\"')
    return f"\"{escaped}\""


def _rewrite_from_template(template_lines: list[str], env_values: dict[str, str]) -> tuple[list[str], set[str]]:
    used_keys: set[str] = set()
    out: list[str] = []
    for line in template_lines:
        m = _ASSIGN_RE.match(line)
        if not m or line.lstrip().startswith("#"):
            out.append(line.rstrip("\n"))
            continue
        key = m.group(1)
        used_keys.add(key)
        if key in env_values:
            out.append(f"{key}={_format_value(env_values[key])}")
        else:
            out.append(line.rstrip("\n"))
    return out, used_keys


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean .env using .env.example as a template without printing secrets.")
    ap.add_argument("--in", dest="env_path", default=".env", help="Input .env path (default: .env)")
    ap.add_argument("--template", dest="template_path", default=".env.example", help="Template path (default: .env.example)")
    ap.add_argument("--backup", action="store_true", help="Create a timestamped backup before rewriting")
    args = ap.parse_args()

    env_path = Path(args.env_path)
    template_path = Path(args.template_path)
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    template_lines = template_path.read_text(encoding="utf-8").splitlines()

    if env_path.exists():
        raw_lines = env_path.read_text(encoding="utf-8").splitlines()
        env_values, counts = _parse_env_lines(raw_lines)
    else:
        env_values, counts = {}, {}

    # Ensure FLASK_SECRET_KEY exists and is non-empty; required when REQUIRE_AUTH=true.
    if not env_values.get("FLASK_SECRET_KEY"):
        env_values["FLASK_SECRET_KEY"] = secrets.token_urlsafe(48)

    rewritten, template_keys = _rewrite_from_template(template_lines, env_values)

    extra_keys = sorted(k for k in env_values.keys() if k not in template_keys)
    if extra_keys:
        rewritten.append("")
        rewritten.append("# ===================================")
        rewritten.append("# Extra Keys (not in .env.example)")
        rewritten.append("# ===================================")
        for k in extra_keys:
            rewritten.append(f"{k}={_format_value(env_values[k])}")

    rewritten_text = "\n".join(rewritten).rstrip() + "\n"

    if args.backup and env_path.exists():
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = env_path.with_suffix(env_path.suffix + f".bak_{ts}")
        backup_path.write_text(env_path.read_text(encoding="utf-8"), encoding="utf-8")

    env_path.write_text(rewritten_text, encoding="utf-8")

    # Print only non-sensitive metadata (no values).
    dupes = sorted((k, c) for k, c in counts.items() if c > 1)
    added = [k for k in template_keys if k not in counts and k in env_values]
    # "added" above only captures generated keys; missing template keys remain missing but in output as blank/default.
    print(f"clean_env: wrote {env_path}")
    print(f"clean_env: template={template_path} keys={len(template_keys)}")
    print(f"clean_env: input_keys={len(counts)} dup_keys={len(dupes)} extra_keys={len(extra_keys)}")
    if dupes:
        print("clean_env: deduped_keys=" + ", ".join(k for k, _ in dupes))
    if added:
        print("clean_env: generated_keys=" + ", ".join(sorted(set(added))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

