from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "sync-gitee.yml"


def test_gitee_sync_workflow_uses_pinned_ssh_secrets_and_safe_push():
    src = WORKFLOW.read_text(encoding="utf-8")

    assert "GITEE_SSH_PRIVATE_KEY" in src
    assert "GITEE_KNOWN_HOSTS" in src
    assert "StrictHostKeyChecking yes" in src
    assert "git@gitee.com:jghe/AI_actuarial_inforsearch.git" in src
    assert "git push gitee HEAD:main" in src
    assert "--force" not in src
    assert "--mirror" not in src


def test_runtime_databases_are_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "config/*.db" in gitignore
    assert "*.sqlite" in gitignore
    assert "*.sqlite3" in gitignore
