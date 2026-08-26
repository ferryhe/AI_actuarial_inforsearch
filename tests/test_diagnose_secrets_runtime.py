import json
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_diagnose_secrets_runtime_reports_presence_without_secret_values(tmp_path):
    secret_value = "do-not-print-this-secret"
    token_value = "do-not-print-this-token"
    env_path = tmp_path / ".env"
    config_path = tmp_path / "sites.yaml"
    missing_db = tmp_path / "missing.db"

    env_path.write_text(
        "\n".join(
            [
                f"FASTAPI_SESSION_SECRET={secret_value}",
                f"TOKEN_ENCRYPTION_KEY={Fernet.generate_key().decode()}",
                f"BOOTSTRAP_ADMIN_TOKEN={token_value}",
                f"CONFIG_WRITE_AUTH_TOKEN={token_value}",
                "OPENAI_API_KEY=sk-do-not-print",
            ]
        ),
        encoding="utf-8",
    )
    config_path.write_text("paths:\n  db: missing.db\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/diagnose_secrets_runtime.py",
            "--env",
            str(env_path),
            "--config",
            str(config_path),
            "--db",
            str(missing_db),
            "--json",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert secret_value not in result.stdout
    assert token_value not in result.stdout
    assert "sk-do-not-print" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["secret_presence"]["FASTAPI_SESSION_SECRET"] is True
    assert payload["token_encryption_key"]["valid_fernet"] is True
    assert payload["auth_token_alignment"] == {"bootstrap_matches_config_write": True}
    assert payload["database"]["exists"] is False


def test_removed_endpoint_tokens_have_no_active_runtime_config_or_documentation_references():
    removed_names = ("LOGS_READ_AUTH_TOKEN", "FILE_DELETION_AUTH_TOKEN")
    paths = [
        *sorted((REPO_ROOT / "ai_actuarial").rglob("*.py")),
        *sorted((REPO_ROOT / "scripts").rglob("*.py")),
        *sorted((REPO_ROOT / "docs").rglob("*.md")),
        REPO_ROOT / ".env.example",
        REPO_ROOT / "docker-compose.yml",
        REPO_ROOT / "docker-compose.override.yml",
        REPO_ROOT / "README.md",
        REPO_ROOT / "README.zh-CN.md",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")
        for name in removed_names:
            assert name not in source, f"{name} remains in {path.relative_to(REPO_ROOT)}"
