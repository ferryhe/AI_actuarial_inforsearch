from __future__ import annotations

import hashlib
import json
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from ai_actuarial import postgres
from ai_actuarial.agent_runtime.artifacts import ArtifactError, ArtifactStore, RevisionConflict
from ai_actuarial.api.deps import AuthContext
from ai_actuarial.features.assistant import feature as host
from ai_actuarial.postgres import PostgresConnection, initialize_postgresql_schema
from ai_actuarial.skills.test_lookup.manifest import ARGUMENT_MODELS
from ai_actuarial.skills.test_lookup.manifest import MANIFEST as TEST_MANIFEST
from scripts import production_recovery
from scripts.production_recovery import _database_report
from tests.postgres_helpers import postgres_url_for_path, uninitialized_postgres_url_for_path


def _package(tmp_path: Path, version: str = "1.0") -> Path:
    root = tmp_path / f"package-{version}"
    root.mkdir()
    source = Path("ai_actuarial/skills/test_lookup")
    shutil.copy2(source / "skill.json", root / "skill.json")
    (root / "SKILL.md").write_text(f"Instructions for {version}", encoding="utf-8")
    manifest = json.loads((root / "skill.json").read_text("utf-8"))
    manifest["version"] = version
    (root / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def _store(tmp_path: Path) -> ArtifactStore:
    url = postgres_url_for_path(tmp_path / "db")
    return ArtifactStore(
        url,
        tmp_path / "data",
        executors=frozenset({"test_lookup.search", "test_lookup.detail"}),
        argument_models=ARGUMENT_MODELS,
        registered_tools=TEST_MANIFEST.tools,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("arguments_model", "DetailArgs"),
        ("executor", "test_lookup.detail"),
        ("tool_id", "test_lookup.unregistered"),
        ("result_kind", "catalog_discovery"),
    ],
)
def test_candidate_requires_registered_tool_contract(
    tmp_path: Path, field: str, value: str
) -> None:
    store = _store(tmp_path)
    package = _package(tmp_path)
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest["tools"][0][field] = value
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="tool contract"):
        _import(store, package)
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert db.execute("SELECT COUNT(*) FROM agent_skill_releases").fetchone()[0] == 0
    finally:
        db.close()
    assert store.slots(feature_key="assistant", site_key="default") == {}


def test_candidate_cannot_remove_registered_tool_scope(tmp_path: Path) -> None:
    store = _store(tmp_path)
    package = _package(tmp_path)
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest["tools"][0]["required_scopes"] = []
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="scope"):
        _import(store, package)
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert db.execute("SELECT COUNT(*) FROM agent_skill_releases").fetchone()[0] == 0
    finally:
        db.close()


def test_repeating_active_release_preserves_previous_rollback_target(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = _import(store, _package(tmp_path))
    second = _import(store, _package(tmp_path, "1.1"))
    store.activate(feature_key="assistant", site_key="default", changes={"test_lookup": (first, 0)})
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (second, 1)}
    )
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (second, 2)}
    )
    slot = store.slots(feature_key="assistant", site_key="default")["test_lookup"]
    assert slot == {"active": second, "previous": first, "revision": 3}
    store.rollback(
        feature_key="assistant", site_key="default", skill_key="test_lookup", expected_revision=3
    )
    assert store.resolve_active(feature_key="assistant", site_key="default")[1] == {
        "test_lookup": first
    }


def _receipt(package: Path) -> dict:
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    artifacts = manifest.get("artifacts") or [{"artifact_id": "instructions", "path": "SKILL.md"}]
    return {
        "result": "PASS",
        "evidence": "fixture",
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
        "code_sha": "a" * 64,
        "data_version": "kb:fixture",
        "model": "stub",
    }


def _import(store: ArtifactStore, package: Path) -> str:
    return store.import_source(
        package,
        feature_key="assistant",
        source_ref="git:test",
        uat=_receipt(package),
        code_sha="a" * 64,
        data_version="kb:fixture",
        model="stub",
    )


def test_import_accepts_full_git_sha1_code_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    package = _package(tmp_path)
    receipt = _receipt(package)
    receipt["code_sha"] = "b" * 40
    release = store.import_source(
        package,
        feature_key="assistant",
        source_ref="git:fixture",
        uat=receipt,
        code_sha="b" * 40,
        data_version="kb:fixture",
        model="stub",
    )
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert (
            db.execute(
                "SELECT validation_jsonb FROM agent_skill_releases WHERE release_id=?", (release,)
            ).fetchone()[0]["code_sha"]
            == "b" * 40
        )
    finally:
        db.close()


def test_concurrent_different_skill_activations_keep_compatible_set(
    tmp_path: Path, monkeypatch
) -> None:
    store = _store(tmp_path)
    first = _import(store, _package(tmp_path))
    package = _package(tmp_path, "1.1")
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest["skill_id"] = "second"
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    second = _import(store, package)
    ready = threading.Event()
    second_at_lock = threading.Event()
    release_first = threading.Event()
    original_commit = PostgresConnection.commit
    original_execute = PostgresConnection.execute

    def delayed_commit(db):
        if threading.current_thread().name == "first":
            ready.set()
            assert release_first.wait(10)
        return original_commit(db)

    def observed_execute(db, sql, parameters=None):
        if threading.current_thread().name == "second" and "pg_advisory_xact_lock" in sql:
            assert not release_first.is_set()
            second_at_lock.set()
        return original_execute(db, sql, parameters)

    monkeypatch.setattr(PostgresConnection, "commit", delayed_commit)
    monkeypatch.setattr(PostgresConnection, "execute", observed_execute)
    successes = []
    failures = []

    def publish(skill, release):
        try:
            store.activate(
                feature_key="assistant", site_key="default", changes={skill: (release, 0)}
            )
            successes.append(skill)
        except Exception as exc:
            failures.append(exc)

    first_thread = threading.Thread(target=publish, name="first", args=("test_lookup", first))
    second_thread = threading.Thread(target=publish, name="second", args=("second", second))
    first_thread.start()
    assert ready.wait(10)
    second_thread.start()
    try:
        assert second_at_lock.wait(10)
    finally:
        release_first.set()
    first_thread.join(10)
    second_thread.join(10)
    assert not first_thread.is_alive() and not second_thread.is_alive()
    assert len(successes) == 1 and len(failures) == 1
    assert "Duplicate tool ID" in str(failures[0])
    assert len(store.resolve_active(feature_key="assistant", site_key="default")[1]) == 1


def _with_eval(package: Path) -> Path:
    (package / "eval_cases.json").write_text('{"case":"sample"}', encoding="utf-8")
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest["artifacts"] = [
        {"artifact_id": "instructions", "kind": "instructions", "path": "SKILL.md"},
        {"artifact_id": "eval_cases", "kind": "eval", "path": "eval_cases.json"},
    ]
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package


def test_draft_requires_validation_before_publication(tmp_path: Path) -> None:
    store = _store(tmp_path)
    package = _with_eval(_package(tmp_path))
    release = store.import_source(
        package,
        feature_key="assistant",
        source_ref="git:draft",
        uat=None,
        code_sha="a" * 64,
        data_version="kb:fixture",
        model="stub",
        draft=True,
    )
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert (
            db.execute(
                "SELECT status FROM agent_skill_releases WHERE release_id=?", (release,)
            ).fetchone()[0]
            == "draft"
        )
    finally:
        db.close()
    with pytest.raises(ArtifactError):
        store.activate(
            feature_key="assistant", site_key="default", changes={"test_lookup": (release, 0)}
        )
    assert store.resolve_active(feature_key="assistant", site_key="default")[1] == {}
    bad = _receipt(package)
    bad["version"] = "9.0"
    with pytest.raises(ArtifactError, match="UAT"):
        store.validate_draft(release, uat=bad)
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert (
            db.execute(
                "SELECT status FROM agent_skill_releases WHERE release_id=?", (release,)
            ).fetchone()[0]
            == "draft"
        )
    finally:
        db.close()
    digest = _receipt(package)["artifact_digests"]["eval_cases"]
    path = store.root / "sha256" / digest
    path.write_bytes(b"corrupt")
    with pytest.raises(ArtifactError, match="checksum"):
        store.validate_draft(release, uat=_receipt(package))
    with pytest.raises(ArtifactError):
        store.activate(
            feature_key="assistant", site_key="default", changes={"test_lookup": (release, 0)}
        )
    path.write_bytes((package / "eval_cases.json").read_bytes())
    assert store.slots(feature_key="assistant", site_key="default") == {}
    store.validate_draft(release, uat=_receipt(package))
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert (
            db.execute(
                "SELECT status FROM agent_skill_releases WHERE release_id=?", (release,)
            ).fetchone()[0]
            == "validated"
        )
    finally:
        db.close()
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (release, 0)}
    )
    assert store.resolve_active(feature_key="assistant", site_key="default")[1] == {
        "test_lookup": release
    }


def _inline_only(package: Path) -> Path:
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest["artifacts"] = [
        {
            "artifact_id": "instructions",
            "kind": "instructions",
            "inline_text": "Inline recovery fixture",
        }
    ]
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package


def test_inline_only_release_full_backup_without_artifact_directory(
    tmp_path: Path, monkeypatch
) -> None:
    store = _store(tmp_path)
    package = _inline_only(_package(tmp_path))
    release = _import(store, package)
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (release, 0)}
    )
    assert not store.root.exists()
    for name in ("rag", "agentic_ready_data"):
        (store.root.parent / name).mkdir(parents=True)
    config = tmp_path / "sites.yaml"
    config.write_text("paths:\n  data: data\n", encoding="utf-8")
    monkeypatch.setattr(
        postgres, "run_postgres_dump", lambda _db, dest, **_kw: Path(dest).write_bytes(b"fixture")
    )
    monkeypatch.setattr(postgres, "verify_postgres_dump", lambda _path: None)
    backup = production_recovery.create_backup(
        data_dir=store.root.parent,
        config_path=config,
        backup_root=tmp_path / "backups",
        include_data=True,
        quiesced=True,
        database_url=store.database_url,
    )
    assert production_recovery.verify_backup(backup)["status"] == "ok"
    assert (
        "agent_artifacts"
        not in json.loads((backup / "manifest.json").read_text("utf-8"))[
            "included_data_directories"
        ]
    )
    assert not store.root.exists()


@pytest.mark.parametrize(
    "field,bad",
    [
        ("skill_id", "other"),
        ("version", "9.0"),
        ("artifact_digests", {"instructions": "0" * 64}),
        ("code_sha", "0" * 64),
        ("data_version", "old-kb"),
        ("model", "other-model"),
        ("approval", "REJECTED"),
        ("unexpected", "extra"),
    ],
)
def test_mismatched_or_rejected_uat_cannot_validate(tmp_path: Path, field: str, bad) -> None:
    store = _store(tmp_path)
    package = _package(tmp_path)
    receipt = _receipt(package)
    receipt[field] = bad
    with pytest.raises(ArtifactError, match="UAT"):
        store.import_source(
            package,
            feature_key="assistant",
            source_ref="git:test",
            uat=receipt,
            code_sha="a" * 64,
            data_version="kb:fixture",
            model="stub",
        )
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        assert db.execute("SELECT COUNT(*) FROM agent_skill_releases").fetchone()[0] == 0
    finally:
        db.close()


def test_backup_verify_checks_release_digest_even_if_directory_stats_match(
    tmp_path: Path, monkeypatch
) -> None:
    store = _store(tmp_path)
    package = _with_eval(_package(tmp_path))
    release = _import(store, package)
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (release, 0)}
    )
    for name in ("rag", "agentic_ready_data"):
        (store.root.parent / name).mkdir()
    config = tmp_path / "sites.yaml"
    config.write_text("paths:\n  data: data\n", encoding="utf-8")
    monkeypatch.setattr(
        postgres, "run_postgres_dump", lambda _db, dest, **_kw: Path(dest).write_bytes(b"fixture")
    )
    monkeypatch.setattr(postgres, "verify_postgres_dump", lambda _path: None)
    backup = production_recovery.create_backup(
        data_dir=store.root.parent,
        config_path=config,
        backup_root=tmp_path / "backups",
        include_data=True,
        quiesced=True,
        database_url=store.database_url,
    )
    digest = _receipt(package)["artifact_digests"]["eval_cases"]
    (backup / "data" / "agent_artifacts" / "sha256" / digest).write_bytes(b"corrupt")
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["data_directories"]["agent_artifacts"] = production_recovery._directory_stats(
        backup / "data" / "agent_artifacts"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RuntimeError, match="artifact"):
        production_recovery.verify_backup(backup)


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_non_instruction_artifact_blocks_activation_and_resolution(
    tmp_path: Path, damage: str
) -> None:
    store = _store(tmp_path)
    baseline = _import(store, _package(tmp_path))
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (baseline, 0)}
    )
    package = _with_eval(_package(tmp_path, "1.1"))
    release = _import(store, package)
    digest = _receipt(package)["artifact_digests"]["eval_cases"]
    path = store.root / "sha256" / digest
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    with pytest.raises(ArtifactError):
        store.activate(
            feature_key="assistant", site_key="default", changes={"test_lookup": (release, 1)}
        )
    assert store.slots(feature_key="assistant", site_key="default")["test_lookup"] == {
        "active": baseline,
        "previous": None,
        "revision": 1,
    }
    path.write_bytes((package / "eval_cases.json").read_bytes())
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (release, 1)}
    )
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    with pytest.raises(ArtifactError):
        store.resolve_active(feature_key="assistant", site_key="default")


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_full_backup_rejects_broken_published_artifact(
    tmp_path: Path, monkeypatch, damage: str
) -> None:
    store = _store(tmp_path)
    package = _with_eval(_package(tmp_path))
    release = _import(store, package)
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (release, 0)}
    )
    digest = _receipt(package)["artifact_digests"]["eval_cases"]
    path = store.root / "sha256" / digest
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")
    for name in ("rag", "agentic_ready_data"):
        (store.root.parent / name).mkdir()
    config = tmp_path / "sites.yaml"
    config.write_text("paths:\n  data: data\n", encoding="utf-8")
    monkeypatch.setattr(
        postgres, "run_postgres_dump", lambda _db, dest, **_kw: Path(dest).write_bytes(b"fixture")
    )
    monkeypatch.setattr(postgres, "verify_postgres_dump", lambda _path: None)
    with pytest.raises(RuntimeError, match="artifact"):
        production_recovery.create_backup(
            data_dir=store.root.parent,
            config_path=config,
            backup_root=tmp_path / "backups",
            include_data=True,
            quiesced=True,
            database_url=store.database_url,
        )


def test_release_cas_rollback_pin_and_durable_read(tmp_path: Path) -> None:
    store = _store(tmp_path)
    initialize_postgresql_schema(store.database_url)
    first = _import(store, _package(tmp_path))
    second = _import(store, _package(tmp_path, "1.1"))
    with pytest.raises(ArtifactError, match="unpublished"):
        store.read(first, "instructions")
    store.activate(feature_key="assistant", site_key="default", changes={"test_lookup": (first, 0)})
    pinned, releases = store.resolve_active(feature_key="assistant", site_key="default")
    assert releases == {"test_lookup": first}
    assert "Instructions for 1.0" in pinned.descriptions()[0]["description"]
    with pytest.raises(RevisionConflict):
        store.activate(
            feature_key="assistant", site_key="default", changes={"test_lookup": (second, 0)}
        )
    store.activate(
        feature_key="assistant", site_key="default", changes={"test_lookup": (second, 1)}
    )
    assert "Instructions for 1.0" in pinned.descriptions()[0]["description"]
    assert (
        store.slots(feature_key="assistant", site_key="default")["test_lookup"]["previous"] == first
    )
    store.rollback(
        feature_key="assistant", site_key="default", skill_key="test_lookup", expected_revision=2
    )
    with pytest.raises(ArtifactError, match="Active or previous"):
        store.retire(first)
    assert store.resolve_active(feature_key="assistant", site_key="default")[1] == {
        "test_lookup": first
    }
    assert (
        ArtifactStore(
            store.database_url,
            tmp_path / "data",
            executors=store.executors,
            argument_models=ARGUMENT_MODELS,
            registered_tools=TEST_MANIFEST.tools,
        ).read(first, "instructions")
        == b"Instructions for 1.0"
    )
    db = PostgresConnection(store.database_url)
    try:
        with pytest.raises(Exception):
            db.execute("UPDATE agent_skill_releases SET version='1.9' WHERE release_id=?", (first,))
        with pytest.raises(Exception):
            db.execute("DELETE FROM agent_skill_releases WHERE release_id=?", (first,))
    finally:
        db.close()


def test_assistant_run_uses_one_pinned_release_snapshot(tmp_path: Path, monkeypatch) -> None:
    store = _store(tmp_path)
    first = _import(store, _package(tmp_path))
    second = _import(store, _package(tmp_path, "1.1"))
    store.activate(feature_key="assistant", site_key="default", changes={"test_lookup": (first, 0)})
    monkeypatch.setenv("DATA_DIR", str(store.root.parent))
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda *_: ("fixture", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **_: None)

    class Storage:
        def __init__(self, _database):
            pass

        def close(self):
            pass

    monkeypatch.setattr(host.chat, "Storage", Storage)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_path=store.database_url)),
        state=SimpleNamespace(),
    )
    auth = AuthContext({"subject": "fixture"}, frozenset({"chat.query"}))
    seen = []

    def model(prompt, _remaining):
        seen.append(prompt)
        if len(seen) == 1:
            store.activate(
                feature_key="assistant", site_key="default", changes={"test_lookup": (second, 1)}
            )
        return json.dumps({"action": "clarify", "question": "Which item?"})

    feature = host.AssistantFeature()
    feature.query(request=request, auth=auth, message="sample", model=model)
    assert request.state.assistant_release_ids == {"test_lookup": first}
    assert "Instructions for 1.0" in seen[0]
    request.state = SimpleNamespace()
    feature.query(request=request, auth=auth, message="sample", model=model)
    assert request.state.assistant_release_ids == {"test_lookup": second}
    assert "Instructions for 1.1" in seen[1]


def test_postgres_without_published_release_cannot_execute_builtin_tool(
    tmp_path: Path, monkeypatch
) -> None:
    store = _store(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(store.root.parent))
    monkeypatch.setattr(host.chat, "_resolve_chat_user", lambda *_: ("fixture", None))
    monkeypatch.setattr(host.chat, "_enforce_chat_quota", lambda **_: None)

    class Storage:
        def __init__(self, _database):
            pass

        def close(self):
            pass

    monkeypatch.setattr(host.chat, "Storage", Storage)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_path=store.database_url)),
        state=SimpleNamespace(),
    )
    auth = AuthContext({"subject": "fixture"}, frozenset({"chat.query"}))
    feature = host.AssistantFeature()
    calls = []
    feature.executors["test_lookup.search"] = lambda args: calls.append(args)
    outcome = feature.query(
        request=request,
        auth=auth,
        message="sample",
        model=lambda *_: json.dumps(
            {
                "action": "call",
                "skill_id": "test_lookup",
                "tool_id": "test_lookup.search",
                "args": {"term": "sample"},
            }
        ),
    )
    assert calls == []
    assert outcome.runtime.error_code == "INVALID_MODEL_RESPONSE"
    assert request.state.assistant_release_ids == {}


def test_invalid_candidate_and_missing_file_do_not_activate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    package = _package(tmp_path)
    with pytest.raises(ArtifactError, match="UAT"):
        store.import_source(
            package,
            feature_key="assistant",
            source_ref="git:test",
            uat={},
            code_sha="a" * 64,
            data_version="kb",
            model="stub",
        )
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest["tools"][0]["executor"] = "unregistered.code"
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="executor"):
        _import(store, package)
    assert store.slots(feature_key="assistant", site_key="default") == {}
    manifest["tools"][0]["executor"] = "test_lookup.search"
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    release = _import(store, package)
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        digest = db.execute(
            "SELECT artifacts_jsonb FROM agent_skill_releases WHERE release_id=?", (release,)
        ).fetchone()[0][0]["sha256"]
    finally:
        db.close()
    (store.root / "sha256" / digest).unlink()
    with pytest.raises(ArtifactError, match="Missing"):
        store.activate(
            feature_key="assistant", site_key="default", changes={"test_lookup": (release, 0)}
        )
    assert store.slots(feature_key="assistant", site_key="default") == {}


def test_multi_skill_switch_is_atomic_and_restore_report_checks_bytes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first_package = _package(tmp_path)
    first = _import(store, first_package)
    second_package = _package(tmp_path, "1.1")
    manifest = json.loads((second_package / "skill.json").read_text("utf-8"))
    manifest["skill_id"] = "second"
    manifest["tools"] = []
    (second_package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    second = _import(store, second_package)
    with pytest.raises(ArtifactError):
        store.activate(
            feature_key="assistant",
            site_key="default",
            changes={
                "test_lookup": (first, 0),
                "second": ("00000000-0000-0000-0000-000000000000", 0),
            },
        )
    assert store.slots(feature_key="assistant", site_key="default") == {}
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes={"test_lookup": (first, 0), "second": (second, 0)},
    )
    assert len(store.resolve_active(feature_key="assistant", site_key="default")[1]) == 2
    assert (
        _database_report(store.database_url, include_counts=True, data_root=store.root.parent)[
            "counts"
        ]["agent_skill_releases"]
        == 2
    )
    instruction = store.read(first, "instructions")
    db = PostgresConnection(store.database_url, read_only=True)
    try:
        digest = db.execute(
            "SELECT artifacts_jsonb FROM agent_skill_releases WHERE release_id=?", (first,)
        ).fetchone()[0][0]["sha256"]
    finally:
        db.close()
    (store.root / "sha256" / digest).write_bytes(b"corrupt")
    with pytest.raises(ArtifactError, match="checksum"):
        store.read(first, "instructions")
    with pytest.raises(RuntimeError, match="corrupt"):
        _database_report(store.database_url, include_counts=True, data_root=store.root.parent)
    assert instruction == b"Instructions for 1.0"


def test_unknown_abi_and_artifact_hash_are_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    package = _package(tmp_path)
    manifest = json.loads((package / "skill.json").read_text("utf-8"))
    manifest["version"] = "2.0"
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="ABI"):
        _import(store, package)
    manifest["version"] = "1.0"
    manifest["schema_version"] = 2
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="manifest"):
        _import(store, package)
    manifest["schema_version"] = 1
    manifest["artifacts"] = [
        {
            "artifact_id": "instructions",
            "kind": "instructions",
            "path": "SKILL.md",
            "sha256": "0" * 64,
        }
    ]
    (package / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ArtifactError, match="checksum"):
        _import(store, package)


def test_migration_failure_rolls_back_and_rerun_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    url = uninitialized_postgres_url_for_path(tmp_path / "fresh")
    broken = tmp_path / "broken.sql"
    broken.write_text(
        "CREATE TABLE transient_skill_table (id integer); INVALID SQL;", encoding="utf-8"
    )
    monkeypatch.setitem(postgres._MIGRATIONS, 8, broken)
    with pytest.raises(Exception):
        initialize_postgresql_schema(url)
    db = PostgresConnection(url, read_only=True)
    try:
        assert not db.table_exists("transient_skill_table")
        assert not db.table_exists("agent_skill_releases")
    finally:
        db.close()
    monkeypatch.undo()
    initialize_postgresql_schema(url)
    initialize_postgresql_schema(url)
    db = PostgresConnection(url, read_only=True)
    try:
        assert db.table_exists("agent_skill_releases")
        assert (
            db.execute("SELECT MAX(version) FROM ai_actuarial_schema_migrations").fetchone()[0] == 8
        )
    finally:
        db.close()


def test_v7_to_v8_preserves_chat_rag_and_feedback_rows(tmp_path: Path, monkeypatch) -> None:
    url = uninitialized_postgres_url_for_path(tmp_path / "v7")
    db = PostgresConnection(url, autocommit=False)
    try:
        for version in range(1, 8):
            db.execute(postgres._MIGRATIONS[version].read_text("utf-8"))
            db.execute("INSERT INTO ai_actuarial_schema_migrations(version) VALUES (?)", (version,))
        db.execute(
            "INSERT INTO conversations(conversation_id,user_id,created_at,updated_at) VALUES ('c-476','u-476','now','now')"
        )
        db.execute(
            "INSERT INTO messages(message_id,conversation_id,role,content,created_at) VALUES ('m-476','c-476','user','kept','now')"
        )
        db.execute(
            "INSERT INTO rag_knowledge_bases(kb_id,name,embedding_model,chunk_size,chunk_overlap,index_type,created_at,updated_at) VALUES ('kb-476','fixture','stub',100,10,'flat','now','now')"
        )
        db.execute(
            "INSERT INTO feedback_items(feedback_id,client_request_id,request_hash,site_key,content,kind,origin,page_path,locale) VALUES ('00000000-0000-0000-0000-000000000476','00000000-0000-0000-0000-000000000477',?,'fixture','kept','suggestion','widget','/','en')",
            ("a" * 64,),
        )
        db.commit()
    finally:
        db.close()
    data = tmp_path / "data"
    for name in ("rag", "agentic_ready_data"):
        (data / name).mkdir(parents=True)
    config = tmp_path / "sites.yaml"
    config.write_text("paths:\n  data: data\n", encoding="utf-8")
    monkeypatch.setattr(
        postgres, "run_postgres_dump", lambda _db, dest, **_kw: Path(dest).write_bytes(b"fixture")
    )
    monkeypatch.setattr(postgres, "verify_postgres_dump", lambda _path: None)
    backup = production_recovery.create_backup(
        data_dir=data,
        config_path=config,
        backup_root=tmp_path / "backups",
        include_data=True,
        quiesced=True,
        database_url=url,
    )
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest.pop("agent_artifacts")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert production_recovery.verify_backup(backup)["status"] == "ok"
    initialize_postgresql_schema(url)
    initialize_postgresql_schema(url)
    db = PostgresConnection(url, read_only=True)
    try:
        assert (
            db.execute("SELECT content FROM messages WHERE message_id='m-476'").fetchone()[0]
            == "kept"
        )
        assert (
            db.execute(
                "SELECT user_id FROM conversations WHERE conversation_id='c-476'"
            ).fetchone()[0]
            == "u-476"
        )
        assert (
            db.execute("SELECT name FROM rag_knowledge_bases WHERE kb_id='kb-476'").fetchone()[0]
            == "fixture"
        )
        assert (
            db.execute("SELECT content FROM feedback_items WHERE site_key='fixture'").fetchone()[0]
            == "kept"
        )
        assert (
            db.execute("SELECT MAX(version) FROM ai_actuarial_schema_migrations").fetchone()[0] == 8
        )
    finally:
        db.close()


def test_issue478_four_packages_publish_and_disable_independently(tmp_path: Path) -> None:
    from ai_actuarial.skills.document_research.manifest import ARGUMENT_MODELS as research_args
    from ai_actuarial.skills.document_research.manifest import MANIFEST as research_manifest
    from ai_actuarial.skills.feedback.manifest import ARGUMENT_MODELS as feedback_args
    from ai_actuarial.skills.feedback.manifest import MANIFEST as feedback_manifest
    from ai_actuarial.skills.resources_updates.manifest import ARGUMENT_MODELS as resource_args
    from ai_actuarial.skills.resources_updates.manifest import MANIFEST as resource_manifest
    from ai_actuarial.skills.usage_navigation.manifest import ARGUMENT_MODELS as usage_args
    from ai_actuarial.skills.usage_navigation.manifest import MANIFEST as usage_manifest

    manifests = (usage_manifest, resource_manifest, research_manifest, feedback_manifest)
    store = ArtifactStore(
        postgres_url_for_path(tmp_path / "db"),
        tmp_path / "data",
        executors=frozenset(tool.executor for item in manifests for tool in item.tools),
        argument_models=usage_args | resource_args | research_args | feedback_args,
        registered_tools=tuple(tool for item in manifests for tool in item.tools),
    )
    releases = {
        item.skill_id: _import(store, Path("ai_actuarial/skills") / item.skill_id)
        for item in manifests
    }
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes={key: (release, 0) for key, release in releases.items()},
    )
    registry, pinned = store.resolve_active(feature_key="assistant", site_key="default")
    assert set(pinned) == set(releases)
    assert {item["skill_id"] for item in registry.descriptions()} == set(releases)

    legacy = tmp_path / "legacy-research"
    shutil.copytree(Path("ai_actuarial/skills/document_research"), legacy)
    legacy_manifest = json.loads((legacy / "skill.json").read_text(encoding="utf-8"))
    legacy_manifest["version"] = "1.0"
    legacy_manifest["tools"][0].pop("result_kind")
    (legacy / "skill.json").write_text(json.dumps(legacy_manifest), encoding="utf-8")
    legacy_release = _import(store, legacy)
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes={"document_research": (legacy_release, 1)},
    )
    legacy_registry, _ = store.resolve_active(feature_key="assistant", site_key="default")
    assert (
        legacy_registry.tool("document_research", "document_research.find_documents").result_kind
        == "catalog_discovery"
    )

    disabled = tmp_path / "disabled"
    shutil.copytree(Path("ai_actuarial/skills/feedback"), disabled)
    manifest = json.loads((disabled / "skill.json").read_text(encoding="utf-8"))
    manifest["enabled"] = False
    manifest["version"] = "1.1"
    (disabled / "skill.json").write_text(json.dumps(manifest), encoding="utf-8")
    disabled_release = _import(store, disabled)
    store.activate(
        feature_key="assistant",
        site_key="default",
        changes={"feedback": (disabled_release, 1)},
    )
    registry, pinned = store.resolve_active(feature_key="assistant", site_key="default")
    assert pinned["feedback"] == disabled_release
    assert {item["skill_id"] for item in registry.descriptions()} == set(releases) - {"feedback"}
    assert registry.tool("document_research", "document_research.find_documents")
