from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "sync-gitee.yml"


def test_gitee_sync_workflow_uses_token_auth_and_safe_push():
    src = WORKFLOW.read_text(encoding="utf-8")

    assert "secrets.GITEE_TOKEN" in src
    assert "vars.GITEE_USER" in src
    assert "git credential approve" in src
    assert "https://gitee.com/${GITEE_USER}/${GITEE_REPOSITORY}.git" in src
    assert "git push gitee HEAD:main" in src
    assert "GITEE_SSH_PRIVATE_KEY" not in src
    assert "GITEE_KNOWN_HOSTS" not in src
    assert "StrictHostKeyChecking" not in src
    assert "--force" not in src
    assert "--mirror" not in src


def test_runtime_databases_are_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "config/*.db" in gitignore
    assert "*.sqlite" in gitignore
    assert "*.sqlite3" in gitignore
