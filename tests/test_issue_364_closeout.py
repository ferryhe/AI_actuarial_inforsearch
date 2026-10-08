"""Small regressions for PR #403's confirmed operational contracts."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from ai_actuarial import build_info
from scripts import production_recovery

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("arguments", [["--help"], ["capacity-check", "--help"]])
def test_host_recovery_help_without_site_packages(arguments):
    result = subprocess.run(
        [sys.executable, "-S", "scripts/production_recovery.py", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_tilde_config_provenance_matches_loaded_file(tmp_path, monkeypatch):
    config = tmp_path / "runtime" / "sites.yaml"
    config.parent.mkdir()
    config.write_text("sites: []\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("CONFIG_PATH", "~/runtime/sites.yaml")
    from ai_actuarial.shared_runtime import load_sites_config

    assert load_sites_config() == {"sites": []}
    info = build_info.detailed_build_info()
    assert info["config_source"] == "external"
    assert info["config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "problem,store",
    [
        (None, "classic"),
        (None, "containerd"),
        (None, "repository"),
        ("missing-config", "containerd"),
        ("missing-config", "repository"),
        ("missing-config", "classic"),
        ("invalid-config", "containerd"),
        ("missing-digest", "classic"),
        ("stale-config", "classic"),
        ("config-as-manifest", "classic"),
        ("missing-target", "classic"),
    ],
)
def test_local_build_metadata_uses_manifest_digest_and_checks_loaded_image(
    tmp_path, problem, store
):
    config = tmp_path / "sites.yaml"
    config.write_text("sites: []\n", encoding="utf-8")
    db = tmp_path / "index.db"
    with sqlite3.connect(db):
        pass
    labels = {
        "com.aiinforsearch.release-id": "fixture-release",
        "org.opencontainers.image.revision": "a" * 40,
        "org.opencontainers.image.created": "2026-10-08T00:00:00Z",
        "org.opencontainers.image.source": "https://example.test/fixture",
        "com.aiinforsearch.git-dirty": "false",
    }
    metadata = {}
    images = {}
    for target, manifest, config_hash in (("api", "b", "c"), ("frontend", "d", "e")):
        metadata[target] = {
            "containerimage.digest": "sha256:" + manifest * 64,
            "containerimage.config.digest": "sha256:" + config_hash * 64,
        }
        images[target] = {
            "Id": "sha256:" + config_hash * 64,
            "RepoDigests": [],
            "Config": {"Labels": labels},
        }
        if store == "containerd":
            images[target]["Id"] = metadata[target]["containerimage.digest"]
            metadata[target]["containerimage.descriptor"] = {
                "mediaType": "application/vnd.oci.image.index.v1+json",
                "digest": metadata[target]["containerimage.digest"],
            }
        elif store == "repository":
            images[target]["Id"] = "sha256:" + "f" * 64
            images[target]["RepoDigests"] = [
                target + "@" + metadata[target]["containerimage.digest"]
            ]
    if problem == "missing-digest":
        del metadata["api"]["containerimage.digest"]
    elif problem == "stale-config":
        metadata["api"]["containerimage.config.digest"] = "sha256:" + "f" * 64
    elif problem == "config-as-manifest":
        metadata["api"]["containerimage.digest"] = metadata["api"]["containerimage.config.digest"]
    elif problem == "missing-target":
        del metadata["frontend"]
    elif problem == "missing-config":
        for target in ("api", "frontend"):
            del metadata[target]["containerimage.config.digest"]
    elif problem == "invalid-config":
        metadata["api"]["containerimage.config.digest"] = "not-a-digest"
    metadata_path = tmp_path / "build.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    output = tmp_path / "release.json"
    arguments = dict(
        image="api",
        frontend_image="frontend",
        config_path=config,
        db_path=db,
        output_path=output,
        build_metadata_path=metadata_path,
        inspect_image=images.__getitem__,
    )
    if problem and not (problem == "missing-config" and store != "classic"):
        with pytest.raises(ValueError):
            production_recovery.create_release_record(**arguments)
        assert not output.exists()
    else:
        record = production_recovery.create_release_record(**arguments)
        assert record["image_digest"] == "sha256:" + "b" * 64
        assert record["image_config_id"] == (
            "unknown" if problem == "missing-config" else "sha256:" + "c" * 64
        )
        assert record["frontend_image_digest"] == "sha256:" + "d" * 64
        assert record["frontend_image_config_id"] == (
            "unknown" if problem == "missing-config" else "sha256:" + "e" * 64
        )
        assert json.loads(output.read_text()) == record
        assert (
            production_recovery.create_release_record(**arguments)["image_digest"]
            == record["image_digest"]
        )


def test_image_config_id_is_never_a_manifest_digest(tmp_path, monkeypatch):
    monkeypatch.setattr(production_recovery, "_require_file", lambda path, _label: path)
    labels = {
        "com.aiinforsearch.release-id": "fixture-release",
        "org.opencontainers.image.revision": "a" * 40,
        "org.opencontainers.image.created": "2026-10-08T00:00:00Z",
        "org.opencontainers.image.source": "https://example.test/fixture",
        "com.aiinforsearch.git-dirty": "false",
    }
    monkeypatch.setattr(
        production_recovery, "_database_report", lambda _: {"schema_user_version": 15}
    )
    monkeypatch.setattr(production_recovery, "config_provenance", lambda _: {})
    output = tmp_path / "release.json"
    with pytest.raises(ValueError, match="manifest digest"):
        production_recovery.create_release_record(
            image="api",
            config_path=Path("fixture"),
            db_path=Path("fixture"),
            output_path=output,
            inspect_image=lambda _: {
                "Id": "sha256:" + "c" * 64,
                "RepoDigests": [],
                "Config": {"Labels": labels},
            },
        )
    assert not output.exists()


@pytest.mark.parametrize(
    "problem", [None, "wrong-loaded-config", "corrupted-manifest", "missing-ref"]
)
def test_raw_bake_metadata_binds_classic_config_through_buildkit_content(
    tmp_path, monkeypatch, problem
):
    """Actual default Bake shape: index digest/build ref, with no config digest."""
    labels = {
        "com.aiinforsearch.release-id": "fixture-release",
        "org.opencontainers.image.revision": "a" * 40,
        "org.opencontainers.image.created": "2026-10-08T00:00:00Z",
        "org.opencontainers.image.source": "https://example.test/fixture",
        "com.aiinforsearch.git-dirty": "false",
    }
    blobs = {}

    def blob(document):
        data = json.dumps(document, separators=(",", ":")).encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        blobs[digest] = data
        return {"digest": digest, "size": len(data)}

    config_descriptor = blob({"config": {"Labels": labels}})
    manifest_descriptor = blob({"schemaVersion": 2, "config": config_descriptor, "layers": []})
    index_descriptor = blob({"schemaVersion": 2, "manifests": [manifest_descriptor]})
    metadata = {
        "api": {
            "containerimage.digest": index_descriptor["digest"],
            "containerimage.descriptor": index_descriptor,
            "buildx.build.ref": "fixture/fixture/build-ref",
        }
    }
    if problem == "missing-ref":
        del metadata["api"]["buildx.build.ref"]
    if problem == "corrupted-manifest":
        blobs[manifest_descriptor["digest"]] = b"{}"
    metadata_path = tmp_path / "build.json"
    metadata_path.write_text(json.dumps(metadata))
    config = tmp_path / "sites.yaml"
    config.write_text("sites: []\n")
    db = tmp_path / "index.db"
    with sqlite3.connect(db):
        pass
    calls = []

    def fetch(argv, **kwargs):
        assert argv[:5] == ["docker", "buildx", "history", "inspect", "attachment"]
        assert argv[5:8] == ["--builder", "fixture", "build-ref"]
        calls.append(argv[8])
        return subprocess.CompletedProcess(argv, 0, blobs[argv[8]], b"")

    monkeypatch.setattr(production_recovery.subprocess, "run", fetch)
    output = tmp_path / "record.json"
    arguments = dict(
        image="api",
        config_path=config,
        db_path=db,
        output_path=output,
        build_metadata_path=metadata_path,
        inspect_image=lambda _: {
            "Id": (
                "sha256:" + "f" * 64
                if problem == "wrong-loaded-config"
                else config_descriptor["digest"]
            ),
            "RepoDigests": [],
            "Config": {"Labels": labels},
        },
    )
    if problem:
        with pytest.raises(ValueError):
            production_recovery.create_release_record(**arguments)
        assert not output.exists()
    else:
        record = production_recovery.create_release_record(**arguments)
        assert record["image_digest"] == index_descriptor["digest"]
        assert record["image_config_id"] == config_descriptor["digest"]
        assert calls == [
            index_descriptor["digest"],
            manifest_descriptor["digest"],
            config_descriptor["digest"],
        ]


@pytest.mark.parametrize("include_config", [True, False])
def test_moby_config_only_metadata_is_rejected_even_with_matching_loaded_id(
    tmp_path, monkeypatch, include_config
):
    """Reproduce the actual Docker28/default-driver config-only exporter shape."""
    content = json.dumps(
        {
            "architecture": "amd64",
            "config": {"Labels": {}},
            "rootfs": {"type": "layers", "diff_ids": []},
            "history": [],
        }
    ).encode()
    config_id = "sha256:" + hashlib.sha256(content).hexdigest()
    metadata = {"containerimage.digest": config_id, "buildx.build.ref": "default/default/build-id"}
    if include_config:
        metadata["containerimage.config.digest"] = config_id
    monkeypatch.setattr(
        production_recovery.subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, content, b""),
    )
    with pytest.raises(ValueError, match="manifest"):
        production_recovery._image_digests({"Id": config_id, "RepoDigests": []}, metadata)
