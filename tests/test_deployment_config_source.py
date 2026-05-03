from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_compose_uses_fastapi_env_and_keeps_features_in_yaml():
    src = (ROOT / "docker-compose.override.yml").read_text(encoding="utf-8")
    lines = {line.strip() for line in src.splitlines()}

    assert "FASTAPI_ENV=production" in src
    assert "- ENV=production" not in lines
    assert "- REQUIRE_AUTH=true" not in lines
    assert "- RATE_LIMIT_ENABLED=true" not in lines
    assert "FASTAPI_CORS_ORIGINS=https://${CADDY_DOMAIN" in src


def test_env_example_documents_comma_separated_cors_origins():
    src = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "FASTAPI_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173" in src
    assert 'FASTAPI_CORS_ORIGINS=["' not in src
