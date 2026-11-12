from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_actuarial import cli
from ai_actuarial.agent_runtime.artifacts import ArtifactError, RevisionConflict
from ai_actuarial.api.deps import AuthContext
from ai_actuarial.api.routers.assistant_runtime import router as runtime_router
from ai_actuarial.assistant.document_research import Document, SectionEvidence, SelectedTarget
from ai_actuarial.features.assistant import feature as host
from ai_actuarial.postgres import PostgresConnection
from ai_actuarial.skills.document_research import executors as research_executors
from ai_actuarial.skills.resources_updates import executors as resources_executors
from ai_actuarial.skills.usage_navigation import executors as usage_executors
from tests.postgres_helpers import postgres_url_for_path

_ROOT = Path(__file__).resolve().parents[1]
_SKILLS = ("usage_navigation", "resources_updates", "document_research")


def _receipt(package: Path, *, code_sha: str, data_version: str, model: str) -> dict:
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    artifacts = manifest.get("artifacts") or [{"artifact_id": "instructions", "path": "SKILL.md"}]
    return {
        "result": "PASS",
        "evidence": "Synthetic receipt for isolated PostgreSQL integration test.",
        "skill_id": manifest["skill_id"],
        "version": manifest["version"],
        "artifact_digests": {
            item["artifact_id"]: hashlib.sha256(
                (package / item["path"]).read_bytes()
                if "path" in item
                else item["inline_text"].encode("utf-8")
            ).hexdigest()
            for item in artifacts
        },
        "code_sha": code_sha,
        "data_version": data_version,
        "model": model,
    }


def _publish_args(receipts: dict[str, Path], *, code_sha: str, revisions: int = 0) -> list[str]:
    args = [
        "--config",
        "config/sites.yaml",
        "assistant-release",
        "publish",
        "--source-ref",
        f"git:{code_sha}",
        "--code-sha",
        code_sha,
        "--data-version",
        "fixture:issue496",
        "--model",
        "stub",
    ]
    for skill_id in _SKILLS:
        args.extend(("--receipt", f"{skill_id}={receipts[skill_id]}"))
    for skill_id in _SKILLS:
        args.extend(("--expected-revision", f"{skill_id}={revisions}"))
    return args + ["--json"]


def _run_cli(args: list[str], capsys) -> tuple[int, dict]:
    parsed = cli.build_parser().parse_args(args)
    code = parsed.func(parsed)
    return code, json.loads(capsys.readouterr().out)


def test_assistant_release_cli_publishes_idempotently_and_serves_public_route(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv("BUILD_GIT_SHA", raising=False)
    monkeypatch.setenv("ASSISTANT_ENABLED", "1")
    monkeypatch.setenv("AI_ACTUARIAL_IGNORE_DOTENV", "1")
    feature = host.AssistantFeature()
    store = feature.artifact_store(postgres_url_for_path(tmp_path / "db"), tmp_path / "data")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "_load_config", lambda _: {"features": {"assistant_enabled": False}})
    code_sha, data_version, model_name = "a" * 64, "fixture:issue496", "stub"
    receipt_paths = {}
    for skill_id in _SKILLS:
        path = tmp_path / f"{skill_id}.receipt.json"
        path.write_text(
            json.dumps(
                _receipt(
                    _ROOT / "ai_actuarial" / "skills" / skill_id,
                    code_sha=code_sha,
                    data_version=data_version,
                    model=model_name,
                )
            ),
            encoding="utf-8",
        )
        receipt_paths[skill_id] = path

    status_code, empty = _run_cli(
        ["--config", "config/sites.yaml", "assistant-release", "status", "--json"], capsys
    )
    assert status_code == 0 and empty["success"]
    assert empty["state"] == "not_ready" and empty["ready"] is False
    assert empty["feature_enabled"] is True
    assert all(item["revision"] == 0 for item in empty["skills"].values())

    expected_source = f"git:{code_sha}"
    staged = store.import_source(
        _ROOT / "ai_actuarial" / "skills" / "usage_navigation",
        feature_key="assistant",
        source_ref=expected_source,
        uat=json.loads(receipt_paths["usage_navigation"].read_text("utf-8")),
        code_sha=code_sha,
        data_version=data_version,
        model=model_name,
    )
    feedback_receipt_path = tmp_path / "feedback.receipt.json"
    feedback_receipt_path.write_text(
        json.dumps(
            _receipt(
                _ROOT / "ai_actuarial" / "skills" / "feedback",
                code_sha=code_sha,
                data_version=data_version,
                model=model_name,
            )
        ),
        encoding="utf-8",
    )
    feedback_release = store.import_source(
        _ROOT / "ai_actuarial" / "skills" / "feedback",
        feature_key="assistant",
        source_ref=expected_source,
        uat=json.loads(feedback_receipt_path.read_text("utf-8")),
        code_sha=code_sha,
        data_version=data_version,
        model=model_name,
    )
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes={"feedback": (feedback_release, 0)},
    )
    code, published = _run_cli(_publish_args(receipt_paths, code_sha=code_sha), capsys)
    assert code == 0 and published["success"] and published["ready"]
    assert published["state"] == "ready"
    assert set(published["activated"]) == set(_SKILLS)
    assert published["release_ids"]["usage_navigation"] == staged
    assert all(published["guide"].values())
    assert sum(len(skill["visible_tools"]) for skill in published["skills"].values()) == 11

    # A repeated invocation validates the receipts but does not insert or bump active slots.
    code, repeated = _run_cli(_publish_args(receipt_paths, code_sha=code_sha, revisions=0), capsys)
    assert code == 0 and repeated["ready"] and repeated["activated"] == []
    assert repeated["release_ids"] == published["release_ids"]
    assert {item["revision"] for item in repeated["skills"].values()} == {1}
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM agent_skill_releases WHERE feature_key='assistant'"
            ).fetchone()[0]
            == 4
        )
    finally:
        db.close()

    url = "https://example.test/soa-report.pdf"
    quote = "The report records 42 observations."
    reference_time = datetime.now(timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return reference_time.astimezone(tz) if tz else reference_time.replace(tzinfo=None)

    monkeypatch.setattr(resources_executors, "datetime", FrozenDateTime)
    first_seen = (reference_time - timedelta(days=1)).date().isoformat()
    target = SelectedTarget(kb_id="public", file_id=url)
    document = Document(
        target=target,
        title="SOA report",
        source_url=url,
        internal_link="/file-detail?url=https%3A%2F%2Fexample.test%2Fsoa-report.pdf",
        publication_date="2026-10-01",
    )
    catalog_row = {
        "title": document.title,
        "url": url,
        "source_name_en": "SOA",
        "summary": "Survey report",
        "published_time": "2026-10-01",
        "first_seen": first_seen,
    }

    class Storage:
        def __init__(self, _database):
            self._conn = SimpleNamespace(
                execute=lambda *_: SimpleNamespace(fetchone=lambda: (url,))
            )

        def query_files_with_catalog(self, **_kwargs):
            return [catalog_row], 1

        def get_source_options(self, **_kwargs):
            return []

        def close(self):
            pass

    class Facade:
        def __init__(self, storage, **_kwargs):
            self.storage = storage

        def _document(self, requested):
            return document if requested == target else None

        def find_documents(self, _query, kb_id=None):
            return [document] if kb_id in (None, "public") else []

        def read_document_sections(self, requested, *, query, section=None):
            return (
                [
                    SectionEvidence(
                        target=requested,
                        section_id="findings",
                        heading="Key Findings",
                        excerpt=quote,
                        source_url=url,
                        retrieval="standard",
                        source_version="fixture-v1",
                    )
                ],
                "ready",
            )

    monkeypatch.setattr(host.chat, "Storage", Storage)
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda *_: ("fixture", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **_: None)
    monkeypatch.setattr(host, "DocumentResearch", Facade)
    auth = AuthContext(
        {"subject": "reader"},
        frozenset({"chat.query", "catalog.read", "files.read", "markdown.read"}),
    )
    monkeypatch.setattr(host.deps, "_load_auth_context", lambda _request: auth)
    app = FastAPI()
    app.state.assistant_enabled = True
    app.state.feedback_enabled = False
    app.state.db_path = store.database_url
    app.state.data_root = tmp_path / "data"
    app.state.assistant_public_kb_ids = ["public"]
    app.state.assistant_staff_kb_ids = []

    guide = usage_executors.guide({"query": "What features are available?", "language": "en"})
    catalog = resources_executors.catalog_search(Facade(Storage(None)), {"query": "SOA"})
    recent_args = {"window_days": 7}
    recent = resources_executors.recent(Facade(Storage(None)), recent_args)
    body_args = {"kb_id": "public", "file_id": url, "query": "findings"}
    body = research_executors.read_document_sections(Facade(None), body_args)

    def script(*outputs):
        pending = list(outputs)

        def model(_prompt, _remaining):
            return json.dumps(pending.pop(0))

        return model

    models = [
        script(
            {
                "action": "call",
                "skill_id": "usage_navigation",
                "tool_id": "usage_navigation.guide",
                "args": {"query": "What features are available?", "language": "en"},
            },
            {"action": "finish", "answer": "Guide answer", "evidence_ids": [guide.evidence_ids[0]]},
        ),
        script(
            {
                "action": "call",
                "skill_id": "resources_updates",
                "tool_id": "resources_updates.catalog_search",
                "args": {"query": "SOA"},
            },
            {
                "action": "finish",
                "answer": "Catalog answer",
                "evidence_ids": [catalog.evidence_ids[0]],
            },
        ),
        script(
            {
                "action": "call",
                "skill_id": "resources_updates",
                "tool_id": "resources_updates.recent",
                "args": recent_args,
            },
            {
                "action": "finish",
                "answer": "Recent answer",
                "evidence_ids": [recent.evidence_ids[0]],
            },
        ),
        script(
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.find_documents",
                "args": {"query": "SOA report"},
            },
            {
                "action": "call",
                "skill_id": "document_research",
                "tool_id": "document_research.read_document_sections",
                "args": body_args,
            },
            {
                "action": "finish",
                "answer": "The findings are supported by the report.",
                "evidence_ids": [body.evidence_ids[0]],
                "findings": [
                    {"evidence_id": body.evidence_ids[0], "quote": quote, "summary": quote}
                ],
            },
            {"supported": [True]},
        ),
    ]
    app.state.assistant_feature = SimpleNamespace(
        query=lambda **kwargs: feature.query(**kwargs, model=models.pop(0))
    )
    app.include_router(runtime_router, prefix="/api")
    with TestClient(app) as client:
        replies = []
        for message in (
            "What features are available?",
            "Find the SOA report",
            "What new materials were collected in the last 7 days?",
            "What are the findings?",
        ):
            response = client.post(
                "/api/assistant/v1/query",
                json={"message": message},
                headers={"X-Auth-Token": "fixture"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["availability"] == "available", f"{message}: {response.text}"
            assert response.json()["intent"] == "answer"
            replies.append(response.json())
        assert "The Dashboard" in replies[0]["answer"]
        assert "1 catalog matches" in replies[1]["answer"]
        assert f"System first collected: {first_seen}" in replies[2]["answer"]
        assert replies[2]["citations"][0]["link"] == document.internal_link
        assert "42 observations" in replies[3]["answer"]
        assert replies[3]["selected_target"] == target.model_dump()
    assert not models


def test_exact_import_rejects_immutable_version_collision_and_rolls_back_one_slot(
    tmp_path, monkeypatch, capsys
):
    feature = host.AssistantFeature()
    store = feature.artifact_store(postgres_url_for_path(tmp_path / "db"), tmp_path / "data")
    package_root = tmp_path / "ai_actuarial" / "skills"
    package_root.mkdir(parents=True)
    shutil.copytree(
        _ROOT / "ai_actuarial" / "skills" / "usage_navigation", package_root / "usage_navigation"
    )
    source = package_root / "usage_navigation"
    receipt = _receipt(source, code_sha="b" * 64, data_version="fixture:v1", model="stub")
    first = store.import_source(
        source,
        feature_key="assistant",
        source_ref="git:old",
        uat=receipt,
        code_sha="b" * 64,
        data_version="fixture:v1",
        model="stub",
    )
    assert (
        store.import_source(
            source,
            feature_key="assistant",
            source_ref="git:new",
            uat=_receipt(source, code_sha="c" * 64, data_version="fixture:v2", model="stub"),
            code_sha="c" * 64,
            data_version="fixture:v2",
            model="stub",
        )
        == first
    )
    manifest = json.loads((source / "skill.json").read_text("utf-8"))
    manifest["version"] = "1.1"
    (source / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    second = store.import_source(
        source,
        feature_key="assistant",
        source_ref="git:new",
        uat=_receipt(source, code_sha="c" * 64, data_version="fixture:v2", model="stub"),
        code_sha="c" * 64,
        data_version="fixture:v2",
        model="stub",
    )
    store.activate(
        feature_key="assistant", site_key="default", changes={"usage_navigation": (first, 0)}
    )
    store.activate(
        feature_key="assistant", site_key="default", changes={"usage_navigation": (second, 1)}
    )
    slot = store.slots(feature_key="assistant", site_key="default")["usage_navigation"]
    assert slot == {"active": second, "previous": first, "revision": 2}
    monkeypatch.setenv("DATABASE_URL", store.database_url)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(cli, "_load_config", lambda _: {"features": {"assistant_enabled": True}})
    rollback_args = cli.build_parser().parse_args(
        [
            "--config",
            "config/sites.yaml",
            "assistant-release",
            "rollback",
            "usage_navigation",
            "--expected-revision",
            "2",
            "--json",
        ]
    )
    assert rollback_args.func(rollback_args) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "partial"
    slot = store.slots(feature_key="assistant", site_key="default")["usage_navigation"]
    assert slot == {"active": first, "previous": second, "revision": 3}
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        row = db.execute(
            "SELECT source_ref,validation_jsonb FROM agent_skill_releases WHERE release_id=?",
            (first,),
        ).fetchone()
        assert row[0] == "git:old" and row[1]["code_sha"] == "b" * 64
    finally:
        db.close()

    collision = tmp_path / "collision"
    shutil.copytree(source, collision)
    (collision / "SKILL.md").write_text(
        "Changed content at the immutable same version.", encoding="utf-8"
    )
    with pytest.raises(ArtifactError, match="Immutable skill version collision"):
        store.import_source(
            collision,
            feature_key="assistant",
            source_ref="git:new",
            uat=_receipt(collision, code_sha="c" * 64, data_version="fixture:v2", model="stub"),
            code_sha="c" * 64,
            data_version="fixture:v2",
            model="stub",
        )


def test_publish_rejects_concurrent_change_to_an_unchanged_slot(tmp_path, monkeypatch):
    from ai_actuarial.assistant import release as release_ops

    monkeypatch.delenv("BUILD_GIT_SHA", raising=False)
    feature = host.AssistantFeature()
    store = feature.artifact_store(postgres_url_for_path(tmp_path / "db"), tmp_path / "data")
    current_sha, current_data, current_model = "e" * 64, "fixture:current", "stub"

    active_releases = {}
    for skill_id in _SKILLS:
        package = _ROOT / "ai_actuarial" / "skills" / skill_id
        active_releases[skill_id] = store.import_source(
            package,
            feature_key="assistant",
            source_ref="git:current",
            uat=_receipt(
                package,
                code_sha=current_sha,
                data_version=current_data,
                model=current_model,
            ),
            code_sha=current_sha,
            data_version=current_data,
            model=current_model,
        )
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes={skill_id: (release_id, 0) for skill_id, release_id in active_releases.items()},
    )

    bundle_file = tmp_path / "bundle" / "ai_actuarial" / "assistant" / "release.py"
    bundle_skills = bundle_file.parents[1] / "skills"
    bundle_skills.mkdir(parents=True)
    packages = {}
    for skill_id in _SKILLS:
        destination = bundle_skills / skill_id
        shutil.copytree(_ROOT / "ai_actuarial" / "skills" / skill_id, destination)
        packages[skill_id] = destination

    resources_manifest_path = packages["resources_updates"] / "skill.json"
    resources_manifest = json.loads(resources_manifest_path.read_text("utf-8"))
    resources_manifest["version"] = "1.9"
    resources_manifest_path.write_text(json.dumps(resources_manifest), encoding="utf-8")
    receipts = {
        skill_id: _receipt(
            package,
            code_sha=current_sha,
            data_version=current_data,
            model=current_model,
        )
        for skill_id, package in packages.items()
    }

    competitor_package = tmp_path / "concurrent-usage-navigation"
    shutil.copytree(packages["usage_navigation"], competitor_package)
    competitor_manifest = json.loads((competitor_package / "skill.json").read_text("utf-8"))
    competitor_manifest["version"] = "1.9"
    (competitor_package / "skill.json").write_text(
        json.dumps(competitor_manifest), encoding="utf-8"
    )
    competing_usage = store.import_source(
        competitor_package,
        feature_key="assistant",
        source_ref="git:concurrent",
        uat=_receipt(
            competitor_package,
            code_sha="f" * 64,
            data_version="fixture:concurrent",
            model=current_model,
        ),
        code_sha="f" * 64,
        data_version="fixture:concurrent",
        model=current_model,
    )

    original_import = store.import_source
    original_activate = store.activate
    interleave = {"phase": "partial", "done": False}

    def import_with_concurrent_operator(source, **kwargs):
        release_id = original_import(source, **kwargs)
        if Path(source).name == "document_research" and not interleave["done"]:
            interleave["done"] = True
            if interleave["phase"] == "partial":
                original_activate(
                    feature_key="assistant",
                    site_key="default",
                    changes={"usage_navigation": (competing_usage, 1)},
                )
            else:
                original_activate(
                    feature_key="assistant",
                    site_key="default",
                    changes={"document_research": (competing_document, 1)},
                )
        return release_id

    monkeypatch.setattr(store, "import_source", import_with_concurrent_operator)
    monkeypatch.setattr(release_ops, "Path", lambda _path: bundle_file)

    with pytest.raises(RevisionConflict, match="active release conflict: usage_navigation"):
        release_ops.publish(
            store,
            feature=feature,
            receipts=receipts,
            expected_revisions={skill_id: 1 for skill_id in _SKILLS},
            source_ref=f"git:{current_sha}",
            code_sha=current_sha,
            data_version=current_data,
            model=current_model,
        )

    slots = store.slots(feature_key="assistant", site_key="default")
    assert interleave["done"]
    assert slots["usage_navigation"] == {
        "active": competing_usage,
        "previous": active_releases["usage_navigation"],
        "revision": 2,
    }
    assert slots["resources_updates"] == {
        "active": active_releases["resources_updates"],
        "previous": None,
        "revision": 1,
    }
    assert slots["document_research"] == {
        "active": active_releases["document_research"],
        "previous": None,
        "revision": 1,
    }

    competitor_document_package = tmp_path / "concurrent-document-research"
    shutil.copytree(
        _ROOT / "ai_actuarial" / "skills" / "document_research", competitor_document_package
    )
    competitor_doc_manifest = json.loads(
        (competitor_document_package / "skill.json").read_text("utf-8")
    )
    competitor_doc_manifest["version"] = "1.9"
    (competitor_document_package / "skill.json").write_text(
        json.dumps(competitor_doc_manifest), encoding="utf-8"
    )
    competing_document = store.import_source(
        competitor_document_package,
        feature_key="assistant",
        source_ref="git:concurrent",
        uat=_receipt(
            competitor_document_package,
            code_sha="f" * 64,
            data_version="fixture:concurrent",
            model=current_model,
        ),
        code_sha="f" * 64,
        data_version="fixture:concurrent",
        model=current_model,
    )

    no_op_bundle_file = tmp_path / "no-op-bundle" / "ai_actuarial" / "assistant" / "release.py"
    no_op_skills = no_op_bundle_file.parents[1] / "skills"
    no_op_skills.mkdir(parents=True)
    no_op_packages = {}
    for skill_id, source in (
        ("usage_navigation", competitor_package),
        ("resources_updates", _ROOT / "ai_actuarial" / "skills" / "resources_updates"),
        ("document_research", _ROOT / "ai_actuarial" / "skills" / "document_research"),
    ):
        destination = no_op_skills / skill_id
        shutil.copytree(source, destination)
        no_op_packages[skill_id] = destination
    no_op_receipts = {
        skill_id: _receipt(
            package,
            code_sha=current_sha,
            data_version=current_data,
            model=current_model,
        )
        for skill_id, package in no_op_packages.items()
    }

    interleave.update(phase="no_op", done=False)
    monkeypatch.setattr(release_ops, "Path", lambda _path: no_op_bundle_file)
    with pytest.raises(RevisionConflict, match="active release conflict: document_research"):
        release_ops.publish(
            store,
            feature=feature,
            receipts=no_op_receipts,
            # This exact no-op must ignore its stale revision snapshot, then guard the IDs.
            expected_revisions={skill_id: 1 for skill_id in _SKILLS},
            source_ref=f"git:{current_sha}",
            code_sha=current_sha,
            data_version=current_data,
            model=current_model,
        )
    slots = store.slots(feature_key="assistant", site_key="default")
    assert interleave["done"]
    assert slots["document_research"] == {
        "active": competing_document,
        "previous": active_releases["document_research"],
        "revision": 2,
    }
    assert slots["resources_updates"]["active"] == active_releases["resources_updates"]
    assert slots["usage_navigation"]["active"] == competing_usage


def test_publish_refuses_to_reenable_an_intentionally_disabled_skill(tmp_path, monkeypatch):
    from ai_actuarial.assistant import release as release_ops

    monkeypatch.delenv("BUILD_GIT_SHA", raising=False)
    feature = host.AssistantFeature()
    store = feature.artifact_store(postgres_url_for_path(tmp_path / "db"), tmp_path / "data")
    package = tmp_path / "disabled-usage"
    shutil.copytree(_ROOT / "ai_actuarial" / "skills" / "usage_navigation", package)
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest.update(enabled=False, version="1.1")
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    code_sha, data_version, model_name = "d" * 64, "fixture:disabled", "stub"
    disabled_release = store.import_source(
        package,
        feature_key="assistant",
        source_ref="git:disabled",
        uat=_receipt(package, code_sha=code_sha, data_version=data_version, model=model_name),
        code_sha=code_sha,
        data_version=data_version,
        model=model_name,
    )
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes={"usage_navigation": (disabled_release, 0)},
    )
    receipts = {
        skill_id: _receipt(
            _ROOT / "ai_actuarial" / "skills" / skill_id,
            code_sha=code_sha,
            data_version=data_version,
            model=model_name,
        )
        for skill_id in _SKILLS
    }
    with pytest.raises(ArtifactError, match="intentionally disabled"):
        release_ops.publish(
            store,
            feature=feature,
            receipts=receipts,
            expected_revisions={
                "usage_navigation": 1,
                "resources_updates": 0,
                "document_research": 0,
            },
            source_ref="git:current",
            code_sha=code_sha,
            data_version=data_version,
            model=model_name,
        )
    assert store.slots(feature_key="assistant", site_key="default") == {
        "usage_navigation": {"active": disabled_release, "previous": None, "revision": 1}
    }


def test_assistant_release_help_and_invalid_receipt_path_are_safe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_ACTUARIAL_IGNORE_DOTENV", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:local@127.0.0.1:1/test")
    monkeypatch.setattr(cli, "_load_config", lambda _: {})
    result = subprocess.run(
        [sys.executable, "-m", "ai_actuarial.cli", "assistant-release", "publish", "--help"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    assert result.returncode == 0
    assert "SKILL=PATH" in result.stdout and "--expected-revision" in result.stdout

    secret_path = tmp_path / "private-uat-receipt.json"
    secret_path.write_text("PRIVATE_RECEIPT_CONTENT_SHOULD_NOT_BE_ECHOED", encoding="utf-8")
    args = [
        "--config",
        "config/sites.yaml",
        "assistant-release",
        "publish",
        "--source-ref",
        "git:test",
        "--code-sha",
        "a" * 64,
        "--data-version",
        "fixture",
        "--model",
        "stub",
    ]
    for skill_id in _SKILLS:
        path = secret_path if skill_id == "usage_navigation" else tmp_path / f"{skill_id}.json"
        args.extend(("--receipt", f"{skill_id}={path}"))
    for skill_id in _SKILLS:
        args.extend(("--expected-revision", f"{skill_id}=0"))
    args.append("--json")
    parsed = cli.build_parser().parse_args(args)
    code = parsed.func(parsed)
    output = capsys.readouterr().out
    assert code == 2
    assert str(secret_path) not in output
    assert "PRIVATE_RECEIPT_CONTENT_SHOULD_NOT_BE_ECHOED" not in output
