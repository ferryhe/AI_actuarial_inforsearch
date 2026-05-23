from pathlib import Path
import shlex

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "sync-gitee.yml"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _run_lines(workflow: dict) -> list[str]:
    steps = workflow["jobs"]["sync"]["steps"]
    runs: list[str] = []
    for step in steps:
        run = step.get("run")
        if run:
            runs.extend(line.strip() for line in run.splitlines() if line.strip())
    return runs


def test_gitee_sync_workflow_uses_token_auth_and_safe_push():
    src = WORKFLOW.read_text(encoding="utf-8")
    workflow = _workflow()
    run_lines = _run_lines(workflow)

    assert "secrets.GITEE_TOKEN" in src
    assert "vars.GITEE_USER" in src
    assert any("git credential approve" in line for line in run_lines)
    assert 'git remote add gitee "https://gitee.com/${GITEE_USER}/${GITEE_REPOSITORY}.git"' in run_lines
    assert "git fetch --prune gitee" in run_lines
    assert "git push --force-with-lease gitee HEAD:main" in run_lines
    assert "GITEE_SSH_PRIVATE_KEY" not in src
    assert "GITEE_KNOWN_HOSTS" not in src
    assert "StrictHostKeyChecking" not in src

    for line in run_lines:
        tokens = shlex.split(line)
        if tokens[:2] == ["git", "push"]:
            assert "--tags" not in tokens
            assert "--force" not in tokens
            assert "--mirror" not in tokens


def test_runtime_databases_are_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "config/*.db" in gitignore
    assert "*.sqlite" in gitignore
    assert "*.sqlite3" in gitignore
