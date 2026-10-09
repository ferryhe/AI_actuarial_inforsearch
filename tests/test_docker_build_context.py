"""Checks Docker's actual build-context filtering behavior."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_docker_build_context_excludes_local_state_and_keeps_build_inputs(tmp_path):
    """Exclude local state while retaining tracked deployment inputs."""
    context = tmp_path / "context"
    context.mkdir()
    shutil.copyfile(ROOT / ".dockerignore", context / ".dockerignore")

    excluded = (
        ".env",
        "nested/.env.production",
        "config/index.db",
        "config/index.db-wal",
        "nested/index.sqlite3.backup",
        ".runtime/sites.yaml",
        "runtime-config/sites.yaml",
        ".codex-tmp-agentic-rag/.env",
        ".codex-tmp-agentic-rag/data/index.db",
        ".hermes/research/receipt.json",
        "graphify-out/index.json",
    )
    retained = (
        "ai_actuarial/api/app.py",
        "ai_actuarial/storage.py",
        "config/yaml_config.py",
        "config/settings.py",
        "config/sites.yaml",
        "config/categories.yaml",
        "config/markdown_conversion.yaml",
        "Dockerfile",
        "Dockerfile.frontend",
        "requirements.txt",
        "package.json",
        "package-lock.json",
        "client/src/main.tsx",
    )
    for relative_path in excluded + retained:
        path = context / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic build context fixture\n", encoding="utf-8")

    exported = tmp_path / "exported"
    result = subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            "--progress=plain",
            "--output",
            f"type=local,dest={exported}",
            "--file",
            "-",
            ".",
        ],
        cwd=context,
        input="FROM scratch\nCOPY . /context/\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-4000:]

    for relative_path in excluded:
        assert not (exported / "context" / relative_path).exists(), relative_path
    for relative_path in retained:
        assert (exported / "context" / relative_path).is_file(), relative_path
