import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_actuarial.api.app import create_app
from scripts import production_recovery

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_provenance_is_safe_and_permission_gated(monkeypatch, tmp_path):
    config = tmp_path / "secret-host-path.yaml"
    config.write_text(
        f"paths:\n  db: {tmp_path / 'index.db'}\nfeatures:\n  require_auth: true\n"
        "sites: []\nscheduled_tasks: []\nprovider_secret: never-expose-this\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(config))
    monkeypatch.setenv("FASTAPI_SESSION_SECRET", "fixture-secret")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_TOKEN", "fixture-admin")
    monkeypatch.setenv("BUILD_RELEASE_ID", "release-fixture-1")
    monkeypatch.setenv("BUILD_GIT_SHA", "a" * 40)
    monkeypatch.setenv("BUILD_UTC", "2026-10-04T12:00:00Z")
    monkeypatch.setenv("API_IMAGE_DIGEST", "sha256:" + "b" * 64)
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "redis://secret-user:secret-pass@host.test/0")

    def no_process(*_args, **_kwargs):
        raise AssertionError("runtime provenance must not run Git or Docker")

    monkeypatch.setattr(subprocess, "run", no_process)
    with TestClient(create_app()) as client:
        public = client.get("/api/health").json()
        assert public["build_info"] == {
            "release_manifest_id": "release-fixture-1",
            "git_sha": "aaaaaaa",
        }
        for endpoint in ("/api/health/detailed", "/api/metrics"):
            assert client.get(endpoint).status_code == 401
            result = client.get(endpoint, headers={"X-Auth-Token": "fixture-admin"})
            assert result.status_code == 200, result.text
            info = result.json()["build_info"]
            assert info == {
                "release_manifest_id": "release-fixture-1",
                "git_sha": "a" * 40,
                "build_utc": "2026-10-04T12:00:00Z",
                "image_digest": "sha256:" + "b" * 64,
                "config_source": "external",
                "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
            }
            assert "never-expose-this" not in result.text
            assert "secret-pass" not in result.text
            assert "secret-host-path" not in result.text
            assert str(tmp_path) not in result.text


def test_invalid_provenance_never_exposes_paths_or_secrets(monkeypatch):
    from ai_actuarial.build_info import get_build_info

    for name in ("BUILD_RELEASE_ID", "BUILD_GIT_SHA", "BUILD_UTC", "API_IMAGE_DIGEST"):
        monkeypatch.setenv(name, "/private/secret?token=secret")
    info = get_build_info()
    assert set(info.values()) == {"unknown"}
    assert "secret" not in json.dumps(info)


def test_production_frontend_uses_immutable_built_artifacts():
    import yaml

    production = yaml.safe_load((ROOT / "docker-compose.override.yml").read_text())
    frontend = production["services"]["frontend"]
    assert frontend["build"]["dockerfile"] == "Dockerfile.frontend"
    assert "/opt/frontend" in frontend["command"]
    dockerfile = (ROOT / "Dockerfile.frontend").read_text()
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "COPY --from=build /app/dist/public /opt/frontend" in dockerfile
    assert "ARG API_IMAGE_DIGEST" not in (ROOT / "Dockerfile").read_text()


def test_vite_only_injects_safe_build_fields():
    environment = {
        **os.environ,
        **{
            name: "/private/path?secret=fixture"
            for name in ("BUILD_RELEASE_ID", "BUILD_GIT_SHA", "BUILD_UTC")
        },
    }
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import {loadConfigFromFile} from 'vite'; const {config}=await loadConfigFromFile({command:'build',mode:'production'},'./vite.config.ts'); console.log(config.define.__BUILD_INFO__);",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == {
        "release_manifest_id": "unknown",
        "git_sha": "unknown",
        "build_utc": "unknown",
    }


def test_compose_build_and_runtime_provenance_contract():
    environment = {
        **os.environ,
        "FASTAPI_SESSION_SECRET": "fixture-compose-secret",
        "TOKEN_ENCRYPTION_KEY": "fixture-key",
        "CONFIG_WRITE_AUTH_TOKEN": "fixture-write-token",
        "RUNTIME_CONFIG_DIR": "./reports/fixture-config",
        "FASTAPI_CORS_ORIGINS": "https://fixture.example.test",
        "VITE_API_BASE_URL": "https://fixture.example.test/api",
        "CADDY_APP_SITE_HOSTS": "fixture.example.test",
        "CADDY_APP_REDIRECT_HOSTS": "fixture.example.test",
        "CADDY_APP_REDIRECT_ORIGIN": "https://fixture.example.test",
        "BUILD_RELEASE_ID": "fixture-compose-release",
        "BUILD_GIT_SHA": "a" * 40,
        "BUILD_UTC": "2026-10-04T12:00:00Z",
        "API_IMAGE_DIGEST": "sha256:" + "b" * 64,
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.override.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    services = json.loads(result.stdout)["services"]
    for service in ("api", "frontend"):
        args = services[service]["build"]["args"]
        assert args["BUILD_RELEASE_ID"] == "fixture-compose-release"
        assert args["BUILD_GIT_SHA"] == "a" * 40
        assert args["BUILD_UTC"] == "2026-10-04T12:00:00Z"
        assert "API_IMAGE_DIGEST" not in args
    assert services["api"]["environment"]["API_IMAGE_DIGEST"] == "sha256:" + "b" * 64


def test_release_record_rejects_frontend_mismatch_and_matches_safe_runtime(tmp_path, monkeypatch):
    import pytest

    config = tmp_path / "private-config.yaml"
    config.write_text("secret: never-expose-this\n", encoding="utf-8")
    db = tmp_path / "index.db"
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA user_version=15")
    labels = {
        "com.aiinforsearch.release-id": "release-one",
        "org.opencontainers.image.revision": "a" * 40,
        "org.opencontainers.image.created": "2026-10-04T12:00:00Z",
        "org.opencontainers.image.source": "https://example.test/repo",
        "com.aiinforsearch.git-dirty": "false",
    }
    images = {
        "api": {
            "Id": "sha256:" + "b" * 64,
            "RepoDigests": ["fixture/api@sha256:" + "b" * 64],
            "Config": {"Labels": labels},
        },
        "frontend": {
            "Id": "sha256:" + "c" * 64,
            "RepoDigests": ["fixture/frontend@sha256:" + "c" * 64],
            "Config": {"Labels": {**labels, "com.aiinforsearch.release-id": "release-two"}},
        },
    }
    output = tmp_path / "release.json"
    with pytest.raises(ValueError, match="provenance mismatch"):
        production_recovery.create_release_record(
            image="api",
            frontend_image="frontend",
            config_path=config,
            db_path=db,
            output_path=output,
            inspect_image=images.__getitem__,
        )
    assert not output.exists()
    images["frontend"]["Config"]["Labels"] = labels
    record = production_recovery.create_release_record(
        image="api",
        frontend_image="frontend",
        config_path=config,
        db_path=db,
        output_path=output,
        inspect_image=images.__getitem__,
    )
    assert record["release_manifest_id"] == "release-one"
    assert record["frontend_image_digest"] == "sha256:" + "c" * 64
    assert record["config_source"] == "external"
    assert "private-config" not in output.read_text()
    from ai_actuarial.build_info import detailed_build_info

    for name, value in {
        "CONFIG_PATH": str(config),
        "BUILD_RELEASE_ID": record["release_manifest_id"],
        "BUILD_GIT_SHA": record["git_sha"],
        "BUILD_UTC": record["build_utc"],
        "API_IMAGE_DIGEST": record["image_digest"],
    }.items():
        monkeypatch.setenv(name, value)
    assert detailed_build_info() == {
        key: record[key]
        for key in (
            "release_manifest_id",
            "git_sha",
            "build_utc",
            "image_digest",
            "config_source",
            "config_sha256",
        )
    }


@pytest.mark.parametrize(
    "ready,include_config_digest,builder_state",
    [
        (True, True, "missing"),
        (True, False, "existing"),
        (False, True, "existing"),
        (False, False, "missing"),
        (True, True, "wrong-driver"),
        (True, True, "create-failed"),
        (True, False, "bootstrap-failed"),
        (True, True, "moby"),
    ],
)
def test_fake_deploy_builds_both_images_before_digest_and_runtime_handoff(
    tmp_path, ready, include_config_digest, builder_state
):
    """Run the real shell flow using only isolated files and fake Docker/Git."""
    import pytest

    bash = shutil.which("bash")
    if sys.platform == "win32":
        bash = str(Path("C:/Program Files/Git/bin/bash.exe"))
    if not bash or not Path(bash).exists():
        pytest.skip("Git Bash or bash is required for the isolated deploy fixture")
    fixture = tmp_path.as_posix()
    commands = tmp_path / "bin"
    commands.mkdir()
    config = tmp_path / "sites.yaml"
    config.write_text("sites: []\n", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    with sqlite3.connect(data / "index.db") as conn:
        conn.execute("PRAGMA user_version=15")
    (tmp_path / "backups").mkdir()
    log = tmp_path / "commands.log"
    blobs = tmp_path / "buildkit-blobs"
    blobs.mkdir()
    identities = {}
    labels = {
        "com.aiinforsearch.release-id": "fixture-canary",
        "org.opencontainers.image.revision": "a" * 40,
        "org.opencontainers.image.created": "2026-10-04T12:00:00Z",
        "org.opencontainers.image.source": "https://github.com/ferryhe/AI_actuarial_inforsearch",
        "com.aiinforsearch.git-dirty": "false",
    }

    def blob(document):
        payload = json.dumps(document, separators=(",", ":")).encode()
        digest = hashlib.sha256(payload).hexdigest()
        (blobs / digest).write_bytes(payload)
        return {"digest": "sha256:" + digest, "size": len(payload)}

    for target in ("api", "frontend"):
        config_blob = blob({"config": {"Labels": labels}, "role": target})
        manifest_blob = blob({"schemaVersion": 2, "config": config_blob, "layers": []})
        index_blob = blob({"schemaVersion": 2, "manifests": [manifest_blob]})
        identities[target] = (index_blob["digest"][7:], config_blob["digest"][7:])

    def executable(name, body):
        path = commands / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body + "\n", encoding="utf-8")
        path.chmod(0o755)

    executable(
        "git",
        'case "$1" in status) ;; rev-parse) printf "%s\\n" "$BUILD_GIT_SHA";; fetch|pull) ;; *) exit 90;; esac',
    )
    executable("flock", "exit 0")
    executable("realpath", 'printf "%s\\n" "$1"')
    executable("stat", 'case "$3" in *backups) echo 2;; *) echo 1;; esac')
    recovery_runner = tmp_path / "recovery_fixture.py"
    recovery_runner.write_text(
        "import os,sys,json\nfrom pathlib import Path\n"
        "sys.path.insert(0, os.environ['REPO_DIR'])\n"
        "from scripts import production_recovery as recovery\n"
        "def inspect(image):\n"
        "    assert Path(os.environ['FIXTURE_BUILT']).exists()\n"
        "    with open(os.environ['FIXTURE_LOG'], 'a') as log: log.write('docker:image inspect '+image+'\\n')\n"
        "    return {'Id':'sha256:'+os.environ['FIXTURE_API_CONFIG' if image==os.environ['API_IMAGE'] else 'FIXTURE_FRONTEND_CONFIG'],'RepoDigests':[],'Config':{'Labels':{'com.aiinforsearch.release-id':os.environ['BUILD_RELEASE_ID'],'org.opencontainers.image.revision':os.environ['BUILD_GIT_SHA'],'org.opencontainers.image.created':os.environ['BUILD_UTC'],'org.opencontainers.image.source':os.environ['BUILD_SOURCE_URL'],'com.aiinforsearch.git-dirty':'false'}}}\n"
        "recovery.create_release_record.__kwdefaults__['inspect_image'] = inspect\n"
        "native_run = recovery.subprocess.run\n"
        "def fixture_run(argv, **kwargs):\n"
        "    if sys.platform == 'win32' and argv[0] == 'docker':\n"
        f"        argv = [{bash!r}, {(commands / 'docker').as_posix()!r}, *argv[1:]]\n"
        "    try:\n"
        "        result = native_run(argv, **kwargs)\n"
        "    except recovery.subprocess.CalledProcessError as exc:\n"
        "        Path(os.environ['FIXTURE_LOG']+'.stderr').write_bytes(exc.stderr or b'')\n"
        "        raise\n"
        "    if result.returncode and result.stderr:\n"
        "        error = result.stderr.encode() if isinstance(result.stderr,str) else result.stderr\n"
        "        Path(os.environ['FIXTURE_LOG']+'.stderr').write_bytes(error)\n"
        "    return result\n"
        "recovery.subprocess.run = fixture_run\n"
        "raise SystemExit(recovery.main(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    executable(
        "python3",
        f'''if [[ "$1" == "scripts/production_recovery.py" && ( "$2" == "capacity-check" || "$2" == "backup" ) ]]; then
  printf 'recovery:%s\\n' "$2" >> "$FIXTURE_LOG"
  exit 0
fi
if [[ "$1" == "scripts/production_recovery.py" ]]; then
  shift
  exec "{Path(sys.executable).as_posix()}" "{recovery_runner.as_posix()}" "$@"
fi
exec "{Path(sys.executable).as_posix()}" "$@"''',
    )
    executable(
        "docker",
        """printf 'docker:%s digest=%s release=%s\\n' "$*" "${API_IMAGE_DIGEST:-unset}" "$BUILD_RELEASE_ID" >> "$FIXTURE_LOG"
if [[ "$1 $2" == "volume inspect" ]]; then echo "$FIXTURE_DATA"; exit; fi
if [[ "$1 $2" == "buildx inspect" ]]; then
  if [[ "$3" == "--bootstrap" ]]; then
    [[ "$4" == "$BUILD_BUILDER" ]]
    [[ "$FIXTURE_BUILDER_STATE" != "bootstrap-failed" ]] || exit 96
  else
    [[ "$3" == "$BUILD_BUILDER" ]]
    [[ "$FIXTURE_BUILDER_STATE" != "missing" || -f "$FIXTURE_BUILDER_CREATED" ]] || exit 1
    [[ "$FIXTURE_BUILDER_STATE" != "create-failed" ]] || exit 1
  fi
  if [[ "$FIXTURE_BUILDER_STATE" == "wrong-driver" ]]; then echo 'Driver: docker'; else echo 'Driver: docker-container'; fi
  exit
fi
if [[ "$1 $2" == "buildx create" ]]; then
  [[ "$*" != *--use* ]]
  [[ "$*" == *"--driver docker-container"* ]]
  [[ "$*" == *"memory=$BUILD_BUILDER_MEMORY,memory-swap=$BUILD_BUILDER_MEMORY"* ]]
  [[ "$FIXTURE_BUILDER_STATE" != "create-failed" ]] || exit 97
  touch "$FIXTURE_BUILDER_CREATED"
  exit
fi
if [[ "$1 $2" == "buildx bake" ]]; then
  shift 2
  [[ "$1 $2" == "--builder $BUILD_BUILDER" ]]
  shift 2
  while [[ "$1" == "-f" ]]; do shift 2; done
  [[ "$1 $2 $3" == "--pull --load --metadata-file" ]]
  metadata="$4"
  shift 4
  [[ "$*" == "api frontend" ]]
  python3 -c 'import json,os,sys; from pathlib import Path; Path(sys.argv[1]).write_text(json.dumps({target:{"containerimage.digest":"sha256:"+os.environ["FIXTURE_"+target.upper()+("_CONFIG" if os.environ["FIXTURE_BUILDER_STATE"]=="moby" else "_HASH")],"buildx.build.ref":"fixture/fixture/"+target,**({"containerimage.config.digest":"sha256:"+os.environ["FIXTURE_"+target.upper()+"_CONFIG"]} if os.environ["FIXTURE_INCLUDE_CONFIG"]=="true" else {})} for target in ("api","frontend")}))' "$metadata"
  touch "$FIXTURE_BUILT"
  exit
fi
if [[ "${1:-} ${2:-} ${3:-} ${4:-}" == "buildx history inspect attachment" ]]; then
  python3 -c 'import os,sys; from pathlib import Path; sys.stdout.buffer.write((Path(os.environ["FIXTURE_BLOBS"])/sys.argv[1][7:]).read_bytes())' "${@: -1}"
  exit
fi
if [[ "$1 $2" == "image inspect" ]]; then
  [[ -f "$FIXTURE_BUILT" ]] || exit 91
  python3 -c 'import json,os,sys; print(json.dumps([{"Id": sys.argv[1], "Config": {"Labels": {"com.aiinforsearch.release-id": os.environ["BUILD_RELEASE_ID"], "org.opencontainers.image.revision": os.environ["BUILD_GIT_SHA"], "org.opencontainers.image.created": os.environ["BUILD_UTC"], "org.opencontainers.image.source": os.environ["BUILD_SOURCE_URL"], "com.aiinforsearch.git-dirty": "false"}}}]))' "$3"
  exit
fi
if [[ "$1" == "compose" ]]; then
  shift
  while [[ "$1" == "-f" ]]; do shift 2; done
  case "$1" in
    ps) exit;;
    build) [[ "$*" == "build --pull api frontend" ]]; touch "$FIXTURE_BUILT";;
    images) if [[ "$3" == "api" ]]; then echo "sha256:$FIXTURE_API_HASH"; else echo "sha256:$FIXTURE_FRONTEND_HASH"; fi;;
    up) [[ "$*" == "up -d --wait --wait-timeout 180 api frontend" ]]; [[ "${API_IMAGE_DIGEST:-}" == "sha256:$FIXTURE_API_HASH" ]]; [[ "$FIXTURE_READY" == "true" ]] || { echo 'frontend unhealthy / readiness timeout' >&2; exit 94; };;
    *) exit 92;;
  esac
  exit
fi
exit 93""",
    )
    environment = {
        **os.environ,
        "PATH": commands.as_posix() + os.pathsep + os.environ["PATH"],
        "REPO_DIR": ROOT.as_posix(),
        "CONFIG_PATH": config.as_posix(),
        "BACKUP_ROOT": f"{fixture}/backups",
        "BACKUP_LOCK_FILE": f"{fixture}/backup.lock",
        "RELEASE_DIR": f"{fixture}/releases",
        "BUILD_RELEASE_ID": "fixture-canary",
        "BUILD_GIT_SHA": "a" * 40,
        "BUILD_UTC": "2026-10-04T12:00:00Z",
        "FIXTURE_BIN": commands.as_posix(),
        "FIXTURE_LOG": log.as_posix(),
        "FIXTURE_DATA": data.as_posix(),
        "FIXTURE_BUILT": f"{fixture}/built",
        "FIXTURE_API_HASH": identities["api"][0],
        "FIXTURE_FRONTEND_HASH": identities["frontend"][0],
        "FIXTURE_API_CONFIG": identities["api"][1],
        "FIXTURE_FRONTEND_CONFIG": identities["frontend"][1],
        "FIXTURE_BLOBS": blobs.as_posix(),
        "FIXTURE_INCLUDE_CONFIG": "true" if include_config_digest else "false",
        "FIXTURE_BUILDER_STATE": builder_state,
        "FIXTURE_BUILDER_CREATED": f"{fixture}/builder-created",
        "BUILD_BUILDER": "fixture-provenance",
        "BUILD_BUILDER_MEMORY": "384m",
        "BUILD_BUILDER_CPU_QUOTA": "20000",
        "FIXTURE_READY": "true" if ready else "false",
    }
    environment.pop("API_IMAGE_DIGEST", None)
    environment.pop("RUNTIME_CONFIG_DIR", None)
    result = subprocess.run(
        [
            bash,
            "--noprofile",
            "--norc",
            "-c",
            'if command -v cygpath >/dev/null; then FIXTURE_BIN=$(cygpath -u "$FIXTURE_BIN"); fi; export PATH="$FIXTURE_BIN:$PATH"; exec bash scripts/deploy_update.sh',
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )
    if builder_state in ("wrong-driver", "create-failed", "bootstrap-failed", "moby"):
        assert result.returncode != 0, result.stdout + result.stderr
        assert "Deployment completed" not in result.stdout
        events = log.read_text()
        assert "up -d" not in events
        assert not (tmp_path / "releases/fixture-canary.json").exists()
        if builder_state != "moby":
            assert "buildx bake" not in events
        return
    if not ready:
        assert result.returncode == 94, result.stdout + result.stderr
        assert "Deployment completed" not in result.stdout
        assert "frontend unhealthy" in result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Deployment completed" in result.stdout
    record = json.loads((tmp_path / "releases/fixture-canary.json").read_text())
    assert record["image_digest"] == "sha256:" + identities["api"][0]
    assert record["frontend_image_digest"] == "sha256:" + identities["frontend"][0]
    assert record["image_config_id"] == "sha256:" + identities["api"][1]
    assert record["frontend_image_config_id"] == "sha256:" + identities["frontend"][1]
    events = log.read_text()
    assert "--use" not in events
    assert events.index("buildx inspect --bootstrap") < events.index("buildx bake")
    assert ("buildx create" in events) == (builder_state == "missing")
    assert (
        events.index("buildx bake")
        < events.index("image inspect")
        < events.index("up -d --wait --wait-timeout 180 api frontend")
    )
    assert (
        "up -d --wait --wait-timeout 180 api frontend digest=sha256:" + identities["api"][0]
        in events
    )
    if not include_config_digest:
        assert events.count("buildx history inspect attachment") == 6
