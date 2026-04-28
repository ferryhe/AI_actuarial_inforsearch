from __future__ import annotations

from pathlib import Path

from ai_actuarial.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


def test_cli_exposes_fastapi_api_command_without_legacy_web_command() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if getattr(action, "dest", None) == "cmd")

    choices = set(subparsers.choices)
    assert "api" in choices
    assert "web" not in choices


def test_runtime_tree_no_longer_contains_legacy_web_assets() -> None:
    assert not (ROOT / "ai_actuarial" / "web").exists()


def test_requirements_do_not_include_flask_runtime_dependencies() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    normalized = {
        line.strip().split("==", 1)[0].split(">=", 1)[0].lower()
        for line in requirements
        if line.strip() and not line.strip().startswith("#")
    }

    assert "flask" not in normalized
    assert "flask-limiter" not in normalized
    assert "flask-seasurf" not in normalized
    assert "a2wsgi" not in normalized
