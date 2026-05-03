import json
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet


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
        cwd=Path(__file__).resolve().parents[1],
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
    assert payload["auth_token_alignment"]["bootstrap_matches_config_write"] is True
    assert payload["database"]["exists"] is False
