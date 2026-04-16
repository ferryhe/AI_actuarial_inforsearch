from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "ai_actuarial" / "api"


def test_fastapi_modules_no_longer_import_web_app_directly_except_legacy_mount() -> None:
    offenders: list[str] = []
    for path in sorted(API_ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel == "ai_actuarial/api/app.py":
            stripped = [line.strip() for line in text.splitlines() if "ai_actuarial.web.app" in line]
            assert stripped == ['import ai_actuarial.web.app as legacy_web_app']
            continue
        if "ai_actuarial.web.app" in text:
            offenders.append(rel)
    assert offenders == []


def test_fastapi_create_app_starts_without_web_package(tmp_path: Path) -> None:
    temp_root = tmp_path / "runtime-check"
    temp_root.mkdir()

    shutil.copytree(ROOT / "ai_actuarial", temp_root / "ai_actuarial", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "config", temp_root / "config", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.rmtree(temp_root / "ai_actuarial" / "web")

    script = (
        "from ai_actuarial.api.app import create_app\n"
        "app = create_app()\n"
        "assert app.state.legacy_mount_enabled is False\n"
        "assert app.state.legacy_mount_error\n"
        "assert '/api/health' in app.state.native_paths\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=temp_root,
        env={**os.environ, **{"PYTHONPATH": str(temp_root)}},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
