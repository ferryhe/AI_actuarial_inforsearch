from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "client" / "src"
SETTINGS_TSX = ROOT / "pages" / "Settings.tsx"
I18N_TS = ROOT / "hooks" / "use-i18n.ts"


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


def test_settings_model_routing_keeps_embeddings_editable_with_rebuild_warning():
    src = SETTINGS_TSX.read_text(encoding="utf-8")
    i18n = I18N_TS.read_text(encoding="utf-8")

    assert '{ key: "embeddings", label: t("settings.routing_embeddings"), capability: "embeddings" }' in src
    assert 'data-testid={`button-edit-model-${card.key}`}' in src
    assert 'data-testid={`select-model-${card.key}`}' in src
    assert 'response.rebuild_required' in src
    assert 'data-testid="routing-warning-reindex"' in src
    assert '"settings.routing_saved_reindex_required": "AI routing saved; embeddings changed. Rebuild affected KB indexes before using them in Chat."' in i18n


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


def test_settings_categories_preserve_ai_keywords_alias():
    src = SETTINGS_TSX.read_text(encoding="utf-8")

    assert "setAiFilterKw(res.ai_keywords || res.ai_filter_keywords || [])" in src
    assert "ai_filter_keywords: aiFilterKw" in src
    assert "ai_keywords: aiFilterKw" in src


def test_settings_exposes_markdown_conversion_as_independent_tab():
    src = SETTINGS_TSX.read_text(encoding="utf-8")
    tab_src = (ROOT / "pages" / "settings" / "MarkdownConversionTab.tsx").read_text(encoding="utf-8")
    i18n = I18N_TS.read_text(encoding="utf-8")

    assert 'testId="tab-markdown-conversion"' in src
    assert 'activeTab === "markdown"' in src
    assert "<MarkdownConversionTab />" in src
    assert '"/api/config/markdown-conversion"' in tab_src
    assert 'data-testid="markdown-conversion-tab"' in tab_src
    assert "if (!value.trim()) return" in tab_src
    assert "!Number.isFinite(parsed) || parsed < 0" in tab_src
    assert '"settings.tab_markdown_conversion"' in i18n


def test_settings_exposes_provider_maintenance_actions():
    src = SETTINGS_TSX.read_text(encoding="utf-8")

    assert '"/api/config/provider-credentials/import-env"' in src
    assert '"/api/config/provider-credentials/re-encrypt"' in src
    assert 'apiGet<{ available: Record<string, AvailableModel[]> }>("/api/config/model-catalog?refresh=true")' in src
    assert 'apiDelete(`/api/config/provider-credentials/${providerId}?category=search`)' in src
    assert 'data-testid="button-import-provider-env"' in src
    assert 'data-testid="button-refresh-model-catalog"' in src
    assert 'data-testid="button-reencrypt-credentials"' in src
    assert 'disabled={!oldEncryptionKey.trim() || maintenanceBusy !== null}' in src
