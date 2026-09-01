from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


def _write_yaml(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_explicit_config_path_is_authoritative_and_never_falls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import (
        SitesConfigError,
        get_sites_config_path,
        load_sites_config,
    )
    from config.yaml_config import _get_sites_config_path, invalidate_config_cache, load_yaml_config

    fallback = tmp_path / "config" / "sites.yaml"
    missing = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(fallback, {"marker": "tracked-fallback"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CONFIG_PATH", str(missing))
    monkeypatch.delenv("FASTAPI_ENV", raising=False)
    invalidate_config_cache()

    assert Path(get_sites_config_path()) == missing
    assert _get_sites_config_path() == missing
    with pytest.raises(SitesConfigError, match="does not exist"):
        load_sites_config()
    with pytest.raises(SitesConfigError, match="does not match authoritative"):
        load_sites_config(fallback)
    with pytest.raises(SitesConfigError, match="does not exist"):
        load_yaml_config()


@pytest.mark.parametrize("contents", ["not: [valid", "- not-a-mapping\n"])
def test_external_config_fails_closed_when_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contents: str,
) -> None:
    from ai_actuarial.shared_runtime import SitesConfigError, load_sites_config

    target = tmp_path / "runtime" / "sites.yaml"
    target.parent.mkdir()
    target.write_text(contents, encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(target))

    with pytest.raises(SitesConfigError, match="valid YAML mapping"):
        load_sites_config()


def test_production_requires_an_explicit_external_config_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import SitesConfigError, load_sites_config

    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.setenv("FASTAPI_ENV", "production")

    with pytest.raises(SitesConfigError, match="CONFIG_PATH is required"):
        load_sites_config()


def test_production_rejects_the_tracked_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import (
        TRACKED_SITES_CONFIG_PATH,
        SitesConfigError,
        load_sites_config,
    )

    monkeypatch.setenv("CONFIG_PATH", str(TRACKED_SITES_CONFIG_PATH))
    monkeypatch.setenv("FASTAPI_ENV", "production")

    with pytest.raises(SitesConfigError, match="must not point to the tracked"):
        load_sites_config()


def test_external_config_fails_closed_when_not_writable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import SitesConfigError, load_sites_config

    target = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(target, {"server": {"fastapi_env": "production"}})
    target.chmod(0o444)
    monkeypatch.setenv("CONFIG_PATH", str(target))

    try:
        with pytest.raises(SitesConfigError, match="not writable"):
            load_sites_config()
    finally:
        target.chmod(0o644)


def test_external_config_fails_closed_when_not_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import SitesConfigError, load_sites_config

    target = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(target, {"server": {"fastapi_env": "production"}})
    monkeypatch.setenv("CONFIG_PATH", str(target))
    real_access = os.access

    def deny_target_read(path: object, mode: int) -> bool:
        if Path(path) == target and mode == os.R_OK:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(os, "access", deny_target_read)

    with pytest.raises(SitesConfigError, match="not readable"):
        load_sites_config()


def test_atomic_yaml_write_fsyncs_replaces_and_leaves_no_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import atomic_write_yaml

    target = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(target, {"value": "old"})
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", recording_fsync)
    atomic_write_yaml(target, {"value": "new"})

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"value": "new"}
    assert fsync_calls
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


def test_atomic_yaml_write_preserves_old_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import atomic_write_yaml

    target = tmp_path / "sites.yaml"
    _write_yaml(target, {"value": "old"})

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        atomic_write_yaml(target, {"value": "new"})

    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"value": "old"}
    assert not list(target.parent.glob(f".{target.name}.*.tmp"))


@pytest.mark.skipif(os.name == "nt", reason="POSIX ownership and mode contract")
def test_atomic_yaml_write_preserves_existing_mode_and_owner(tmp_path: Path) -> None:
    from ai_actuarial.shared_runtime import atomic_write_yaml

    target = tmp_path / "sites.yaml"
    _write_yaml(target, {"value": "old"})
    target.chmod(0o640)
    before = target.stat()

    atomic_write_yaml(target, {"value": "new"})

    after = target.stat()
    assert after.st_mode & 0o777 == 0o640
    assert after.st_uid == before.st_uid
    assert after.st_gid == before.st_gid


def test_bootstrap_is_create_once_and_refuses_to_overwrite(
    tmp_path: Path,
) -> None:
    from ai_actuarial.shared_runtime import bootstrap_sites_config

    source = tmp_path / "repo" / "config" / "sites.yaml"
    target = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(source, {"value": "template"})

    created = bootstrap_sites_config(source, target)
    assert created == target.resolve()
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == {"value": "template"}

    target.write_text("value: operator-edit\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists"):
        bootstrap_sites_config(source, target)
    assert target.read_text(encoding="utf-8") == "value: operator-edit\n"


def test_config_bootstrap_cli_reports_creation_and_refuses_overwrite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai_actuarial.cli import build_parser

    source = tmp_path / "repo" / "config" / "sites.yaml"
    target = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(source, {"value": "template"})
    parser = build_parser()
    argv = [
        "--config",
        str(target),
        "config-bootstrap",
        "--source",
        str(source),
        "--json",
    ]

    args = parser.parse_args(argv)
    assert args.func(args) == 0
    assert json.loads(capsys.readouterr().out)["config_path"] == str(target.resolve())

    args = parser.parse_args(argv)
    assert args.func(args) == 2
    error = json.loads(capsys.readouterr().out)
    assert error["success"] is False
    assert "already exists" in error["error"]


def test_production_cli_rejects_implicit_tracked_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai_actuarial import cli

    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.setenv("FASTAPI_ENV", "production")
    monkeypatch.setattr(cli, "_load_dotenv", lambda _path: None)
    monkeypatch.setattr(sys, "argv", ["ai-actuarial", "update"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 2
    assert "must not point to the tracked" in capsys.readouterr().err


def test_schema_status_does_not_require_sites_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from ai_actuarial import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONFIG_PATH", raising=False)
    monkeypatch.delenv("FASTAPI_ENV", raising=False)
    monkeypatch.setattr(cli, "_load_dotenv", lambda _path: None)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ai-actuarial", "schema", "status", "--db", str(tmp_path / "schema.db"), "--json"],
    )

    assert cli.main() == 0
    assert json.loads(capsys.readouterr().out)["state"] == "missing"


def test_legacy_env_migration_refuses_existing_external_config(tmp_path: Path) -> None:
    target = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(target, {"operator_value": "preserve-me"})
    before = target.read_bytes()
    environment = os.environ.copy()
    environment["CONFIG_PATH"] = str(target)
    environment.pop("FASTAPI_ENV", None)

    result = subprocess.run(
        [sys.executable, "scripts/migrate_env_to_yaml.py", "--no-backup"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    assert result.returncode == 1
    assert "Refusing to modify an existing external CONFIG_PATH" in result.stdout
    assert target.read_bytes() == before


def test_external_runtime_config_survives_git_reset_checkout_and_clean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.shared_runtime import (
        atomic_write_yaml,
        bootstrap_sites_config,
        get_sites_config_path,
        load_sites_config,
    )

    repo = tmp_path / "repo"
    tracked = repo / "config" / "sites.yaml"
    external = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(tracked, {"chat_model": "template-model"})
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Issue 310 Test")
    _git(repo, "add", "config/sites.yaml")
    _git(repo, "commit", "-m", "template")

    monkeypatch.setenv("CONFIG_PATH", str(external))
    bootstrap_sites_config(tracked, Path(get_sites_config_path()))
    atomic_write_yaml(external, {"chat_model": "operator-selected-model"})

    tracked.write_text("chat_model: worktree-edit\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("clean me", encoding="utf-8")
    _git(repo, "reset", "--hard", "HEAD")
    _git(repo, "checkout", "--", ".")
    _git(repo, "clean", "-fd")

    assert load_sites_config() == {"chat_model": "operator-selected-model"}
    assert yaml.safe_load(tracked.read_text(encoding="utf-8")) == {"chat_model": "template-model"}


def test_settings_write_changes_only_external_config_and_survives_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.api.services.ops_write import update_backend_settings
    from ai_actuarial.shared_runtime import bootstrap_sites_config, load_sites_config

    repo = tmp_path / "repo"
    tracked = repo / "config" / "sites.yaml"
    external = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(tracked, {"defaults": {"max_pages": 100}, "features": {}})
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Issue 310 Test")
    _git(repo, "add", "config/sites.yaml")
    _git(repo, "commit", "-m", "template")

    bootstrap_sites_config(tracked, external)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CONFIG_PATH", str(external))

    update_backend_settings({"defaults": {"max_pages": 321}})

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    assert status == ""
    assert load_sites_config()["defaults"]["max_pages"] == 321
    assert yaml.safe_load(tracked.read_text(encoding="utf-8"))["defaults"]["max_pages"] == 100


def test_external_config_preserves_shared_chat_weekly_routing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ai_actuarial.ai_runtime import get_ai_function_section
    from ai_actuarial.shared_runtime import load_sites_config

    external = tmp_path / "runtime" / "sites.yaml"
    _write_yaml(
        external,
        {
            "ai_config": {
                "chatbot": {
                    "provider": "deepseek",
                    "model": "deepseek-chat",
                    "credential_id": "deepseek:llm:instance:primary",
                },
                "weekly_explanation": {
                    "provider": "openai",
                    "model": "legacy-weekly-model",
                    "credential_id": "openai:llm:instance:legacy",
                    "prompt": "Keep this weekly policy",
                    "prompt_version": "weekly-v2",
                },
            }
        },
    )
    monkeypatch.setenv("CONFIG_PATH", str(external))

    weekly = get_ai_function_section(
        "weekly_explanation",
        yaml_config=load_sites_config(),
    )

    assert weekly["provider"] == "deepseek"
    assert weekly["model"] == "deepseek-chat"
    assert weekly["credential_id"] == "deepseek:llm:instance:primary"
    assert weekly["prompt"] == "Keep this weekly policy"
    assert weekly["prompt_version"] == "weekly-v2"


def test_cli_and_production_tools_use_the_effective_config_path() -> None:
    from ai_actuarial.cli import build_parser

    help_text = build_parser().format_help()
    assert "config-bootstrap" in help_text

    backup = Path("scripts/production_backup.sh").read_text(encoding="utf-8")
    full_backup = Path("scripts/production_full_backup.sh").read_text(encoding="utf-8")
    deploy = Path("scripts/deploy_update.sh").read_text(encoding="utf-8")
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    production_compose = Path("docker-compose.override.yml").read_text(encoding="utf-8")

    assert 'CONFIG_PATH="${CONFIG_PATH:?' in backup
    assert 'CONFIG_PATH="${CONFIG_PATH:?' in full_backup
    assert 'CONFIG_PATH="${CONFIG_PATH:?' in deploy
    assert deploy.count('--config "$CONFIG_PATH"') == 2
    assert 'expected_config_dir=$(dirname "$CONFIG_PATH")' in deploy
    assert "RUNTIME_CONFIG_DIR must be the directory containing CONFIG_PATH" in deploy
    assert "CONFIG_FILENAME must be the basename of CONFIG_PATH" in deploy
    assert "CONFIG_PATH=/app/runtime-config/${CONFIG_FILENAME:-sites.yaml}" in compose
    assert "${RUNTIME_CONFIG_DIR:-./config}:/app/runtime-config:rw" in compose
    assert "${RUNTIME_CONFIG_DIR:?" in production_compose
