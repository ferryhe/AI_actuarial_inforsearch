from __future__ import annotations

import os
from pathlib import Path

import yaml

from ai_actuarial.task_runtime import NativeTaskRuntime
from ai_actuarial.web_listening_rule import generate_draft_rule, materialize_rule, rule_to_yaml, validate_rule
from tests.test_fastapi_ops_read_endpoints import _build_test_client, _patch_available_models
from tests.test_fastapi_ops_write_endpoints import _BridgeRecorder, _install_bridge, _install_public_dns_resolver


def test_web_listening_rule_draft_validate_and_materialize_helpers(monkeypatch) -> None:
    _install_public_dns_resolver(monkeypatch, "example.com")
    rule = generate_draft_rule(website_url="https://example.com/research", goal="Monitor actuarial AI research reports")

    assert rule.schema_version == "web-listening-agent-rule.v1"
    assert rule.acquisition_profile.name == "Web Listening: example.com"
    assert rule.acquisition_profile.tools == ["crawler", "search"]
    assert rule.acquisition_profile.content_types == ["file", "webpage"]
    assert rule.section_selection.content_selector == "main"
    assert rule.section_selection.allow_url_patterns == ["/research"]
    assert "actuarial" in rule.monitor_scope.keywords

    normalized, errors, warnings = validate_rule(rule_to_yaml(rule))
    assert errors == []
    assert normalized is not None
    assert warnings == []

    materialized = materialize_rule(normalized)
    assert materialized.site["name"] == "Web Listening: example.com"
    assert materialized.site["collect_page_content"] is True
    assert materialized.site["collect_linked_files"] is True
    assert materialized.site["acquisition_tools"] == ["crawler", "search"]
    assert materialized.site["content_selector"] == "main"
    assert materialized.site["allow_url_patterns"] == ["/research"]
    assert materialized.scheduled_task["type"] == "scheduled"
    assert materialized.scheduled_task["params"]["site"] == "Web Listening: example.com"
    assert materialized.scheduled_task["params"]["name"] == "Scheduled: Web Listening: example.com"



def test_web_listening_rule_infers_query_for_selected_content_type() -> None:
    webpage_rule = generate_draft_rule(
        website_url="https://example.com/articles",
        goal="Monitor actuarial AI articles",
        tools=["search"],
        content_types=["webpage"],
    )
    assert webpage_rule.monitor_scope.queries == ["site:example.com Monitor actuarial AI articles"]
    webpage_site = materialize_rule(webpage_rule).site
    assert webpage_site["collect_linked_files"] is False
    assert webpage_site["collect_page_content"] is True

    file_rule = generate_draft_rule(
        website_url="https://example.com/reports",
        goal="Monitor actuarial AI reports",
        tools=["search"],
        content_types=["file"],
    )
    assert file_rule.monitor_scope.queries == [
        "site:example.com Monitor actuarial AI reports filetype:pdf"
    ]

def test_web_listening_rule_validation_reports_errors(monkeypatch) -> None:
    rule, errors, warnings = validate_rule(
        {
            "schema_version": "web-listening-agent-rule.v1",
            "acquisition_profile": {"name": "Bad", "website_url": "ftp://example.com", "goal": "AI"},
            "monitor_task": {"name": "Bad Monitor", "schedule_interval": "hourly"},
        }
    )
    assert rule is None
    assert errors
    assert warnings == []


def test_web_listening_rule_requires_non_empty_strategy_and_queries_for_search() -> None:
    base = {
        "schema_version": "web-listening-agent-rule.v1",
        "acquisition_profile": {
            "name": "Strategy",
            "website_url": "https://example.com",
            "goal": "Monitor research",
            "tools": [],
            "content_types": [],
        },
        "monitor_task": {"name": "Strategy Monitor"},
    }
    rule, errors, _warnings = validate_rule(base, check_url_safety=False)
    assert rule is None
    assert any("tools" in error for error in errors)
    assert any("content_types" in error for error in errors)

    base["acquisition_profile"]["tools"] = ["search"]
    base["acquisition_profile"]["content_types"] = ["webpage"]
    rule, errors, _warnings = validate_rule(base, check_url_safety=False)
    assert rule is None
    assert any("monitor_scope.queries" in error for error in errors)


def test_web_listening_rule_routes_materialize_idempotently(tmp_path: Path, monkeypatch) -> None:
    _patch_available_models(monkeypatch)
    _install_public_dns_resolver(monkeypatch, "rules.example")
    client, app, seed = _build_test_client(tmp_path, monkeypatch, require_auth=False)
    recorder = _BridgeRecorder()
    _install_bridge(app, recorder)
    headers = {"X-Auth-Token": str(seed["operator_token"])}
    config_path = Path(os.environ["CONFIG_PATH"])

    exploration_html = """
    <html><head><title>Rules Research</title></head><body><main>
      <a href="/insights/generative-ai">Generative AI insight</a>
      <a href="/globalassets/reserving-ai.pdf">Reserving AI report</a>
    </main></body></html>
    """
    monkeypatch.setattr(
        "ai_actuarial.api.services.ops_write.Crawler._request",
        lambda self, url, timeout=15: (
            exploration_html.encode(),
            {"content-type": "text/html"},
            "https://rules.example/insights",
        ),
    )
    exploration = client.post(
        "/api/web-listening/rules/explore",
        json={
            "website_url": "https://rules.example/insights",
            "goal": "Monitor reserving and generative AI publications",
        },
        headers=headers,
    )
    assert exploration.status_code == 200, exploration.text
    exploration_body = exploration.json()
    assert exploration_body["suggestions"]["tools"] == ["crawler"]
    assert exploration_body["suggestions"]["content_types"] == ["file", "webpage"]
    assert exploration_body["suggestions"]["content_selector"] == "main"
    assert "/insights" in exploration_body["suggestions"]["allow_url_patterns"]
    assert exploration_body["observations"]["file_link_count"] == 1

    def blocked_request(_self, _url, timeout=15):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(
        "ai_actuarial.api.services.ops_write.Crawler._request",
        blocked_request,
    )
    blocked_exploration = client.post(
        "/api/web-listening/rules/explore",
        json={
            "website_url": "https://rules.example/blocked",
            "goal": "Monitor blocked research",
        },
        headers=headers,
    )
    assert blocked_exploration.status_code == 200
    blocked_body = blocked_exploration.json()
    assert blocked_body["suggestions"]["tools"] == ["search"]
    assert blocked_body["observations"]["reachable"] is False

    draft = client.post(
        "/api/web-listening/rules/draft",
        json={
            "website_url": "https://rules.example/insights",
            "goal": "Monitor reserving and generative AI publications",
            "name": "Rules Example Insights",
        },
        headers=headers,
    )
    assert draft.status_code == 200, draft.text
    draft_body = draft.json()
    assert draft_body["success"] is True
    assert "schema_version: web-listening-agent-rule.v1" in draft_body["yaml"]

    rule = draft_body["rule"]
    rule["acquisition_profile"]["max_pages"] = 12
    rule["monitor_task"]["schedule_interval"] = "daily at 03:15"
    rule["section_selection"]["allow_url_patterns"] = ["/insights", "/globalassets/"]
    rule["monitor_scope"]["exclude_prefixes"] = ["archive_"]

    validation = client.post("/api/web-listening/rules/validate", json={"rule": rule}, headers=headers)
    assert validation.status_code == 200, validation.text
    validation_body = validation.json()
    assert validation_body["valid"] is True
    assert validation_body["materialized_config"]["site"]["max_pages"] == 12

    first = client.post("/api/web-listening/rules/materialize", json={"rule": rule}, headers=headers)
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body["success"] is True
    assert first_body["requires_scheduler_reinit"] is False
    assert first_body["updated"] == {"site": False, "scheduled_task": False}
    assert recorder.last_site_config is not None

    second = client.post("/api/web-listening/rules/materialize", json={"rule_yaml": first_body["yaml"]}, headers=headers)
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["updated"] == {"site": True, "scheduled_task": True}
    assert second_body["backup"] != first_body["backup"]
    backup_dir = config_path.parent / "backups"
    assert (backup_dir / first_body["backup"]).exists()
    assert (backup_dir / second_body["backup"]).exists()

    written = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    matching_sites = [site for site in written["sites"] if site["name"] == "Rules Example Insights"]
    matching_tasks = [task for task in written["scheduled_tasks"] if task["name"] == "Rules Example Insights Monitor"]
    assert len(matching_sites) == 1
    assert len(matching_tasks) == 1
    site = matching_sites[0]
    assert site["url"] == "https://rules.example/insights"
    assert site["collect_page_content"] is True
    assert site["collect_linked_files"] is True
    assert site["acquisition_tools"] == ["crawler", "search"]
    assert site["content_selector"] == "main"
    assert site["allow_url_patterns"] == ["/insights", "/globalassets/"]
    assert site["exclude_prefixes"] == ["archive_"]
    assert site["web_listening_rule_schema_version"] == "web-listening-agent-rule.v1"
    task = matching_tasks[0]
    assert task["type"] == "scheduled"
    assert task["interval"] == "daily at 03:15"
    assert task["params"]["site"] == "Rules Example Insights"
    assert task["params"]["name"] == "Scheduled: Rules Example Insights"
    assert task["params"]["check_database"] is True

    read_back = client.get("/api/config/sites", headers=headers)
    assert read_back.status_code == 200, read_back.text
    read_site = next(site for site in read_back.json()["sites"] if site["name"] == "Rules Example Insights")
    assert read_site["collect_page_content"] is True
    assert read_site["collect_linked_files"] is True
    assert read_site["acquisition_tools"] == ["crawler", "search"]
    assert read_site["allow_url_patterns"] == ["/insights", "/globalassets/"]


def test_task_runtime_passes_collect_page_content_from_yaml() -> None:
    runtime = NativeTaskRuntime()
    site_configs = runtime._site_configs_for_run(
        {
            "defaults": {"max_pages": 5, "max_depth": 1, "file_exts": [".pdf"]},
            "sites": [
                {
                    "name": "Content Site",
                    "url": "https://content.example",
                    "collect_page_content": "false",
                    "collect_linked_files": "true",
                    "acquisition_tools": ["search"],
                    "content_selector": "article",
                    "allow_url_patterns": ["/research"],
                }
            ],
        },
        {"site": "Content Site"},
    )
    assert len(site_configs) == 1
    assert site_configs[0].collect_page_content is False
    assert site_configs[0].collect_linked_files is True
    assert site_configs[0].acquisition_tools == ["search"]
    assert site_configs[0].content_selector == "article"
    assert site_configs[0].allow_url_patterns == ["/research"]
