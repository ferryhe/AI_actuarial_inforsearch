from __future__ import annotations

from pathlib import Path

LOGS_TSX = Path(__file__).parents[1] / "client" / "src" / "pages" / "Logs.tsx"
I18N_TS = Path(__file__).parents[1] / "client" / "src" / "hooks" / "use-i18n.ts"


def test_logs_page_treats_empty_api_payload_as_zero_entries() -> None:
    source = LOGS_TSX.read_text(encoding="utf-8")

    assert 'apiGet<{ logs: string }>("/api/logs/global")' in source
    assert "setLogs(parseLogs(res.logs))" in source
    assert "No logs found." not in source
    assert 'data-testid="text-no-logs"' in source
    assert 'data-testid="text-log-count"' in source


def test_logs_page_classifies_load_failures_without_calling_every_error_disabled() -> None:
    source = LOGS_TSX.read_text(encoding="utf-8")
    translations = I18N_TS.read_text(encoding="utf-8")

    assert 'status === 401' in source
    assert 'status === 403 && msg === "GLOBAL_LOGS_API_DISABLED"' in source
    assert '? "forbidden"' in source
    assert ': "failed"' in source
    assert "logsApiDisabled" not in source
    for key in ("unauthenticated", "forbidden", "disabled", "failed"):
        assert translations.count(f'"logs.{key}_title"') == 2
        assert translations.count(f'"logs.{key}_desc"') == 2
    assert "ENABLE_GLOBAL_LOGS_API=True" not in translations
    assert "server runtime settings or configuration" in translations
    assert "服务器运行时设置或配置" in translations
