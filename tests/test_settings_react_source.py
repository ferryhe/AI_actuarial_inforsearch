from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
SETTINGS_TSX = ROOT / "pages" / "Settings.tsx"


def test_settings_model_routing_surfaces_backend_error_detail():
    src = SETTINGS_TSX.read_text(encoding="utf-8")

    assert "ApiError" in src
    assert "catch (error)" in src
    assert "error instanceof ApiError" in src
    assert 'error.detail || error.message || t("settings.models_save_error")' in src


def test_settings_model_routing_does_not_round_trip_failed_credentials():
    src = SETTINGS_TSX.read_text(encoding="utf-8")

    assert "function credentialUsable" in src
    assert "credential.decrypt_ok === false" in src
    assert "routing[functionName]?.credential_error ? \"\"" in src
    assert "credentialUsable(credential)" in src


def test_settings_system_flags_are_yaml_backed_controls():
    src = SETTINGS_TSX.read_text(encoding="utf-8")

    assert "const editableFlags" in src
    assert '"enable_global_logs_api"' in src
    assert '"enable_rate_limiting"' in src
    assert '"enable_security_headers"' in src
    assert '"expose_error_details"' in src
    assert '"rate_limit_defaults"' in src
    assert '"rate_limit_storage_uri"' in src
    assert '"content_security_policy"' in src
    assert "featureSources" in src
    assert "...featureText" in src
    assert "toggle-system-flag-${key}" in src
    assert "input-${key.replaceAll(\"_\", \"-\")}" in src
    assert 'apiPost("/api/config/backend-settings", { features:' in src
