from __future__ import annotations

from pathlib import Path

from ai_actuarial.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


def test_cli_exposes_fastapi_api_command_without_legacy_web_command() -> None:
    parser = build_parser()
    subparsers = next(action for action in parser._actions if getattr(action, "dest", None) == "cmd")

    choices = set(subparsers.choices)
    assert "api" in choices
    assert "web" not in choices


def test_runtime_tree_no_longer_contains_legacy_web_assets() -> None:
    assert not (ROOT / "ai_actuarial" / "web").exists()


def test_requirements_do_not_include_flask_runtime_dependencies() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    normalized = {
        line.strip().split("==", 1)[0].split(">=", 1)[0].lower()
        for line in requirements
        if line.strip() and not line.strip().startswith("#")
    }

    assert "flask" not in normalized
    assert "flask-limiter" not in normalized
    assert "flask-seasurf" not in normalized
    assert "a2wsgi" not in normalized


def test_requirements_do_not_include_local_embedding_or_gpu_heavy_dependencies() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    normalized = {
        line.strip().split("==", 1)[0].split(">=", 1)[0].lower()
        for line in requirements
        if line.strip() and not line.strip().startswith("#")
    }

    assert "keybert" not in normalized
    assert "sentence-transformers" not in normalized
    assert "marker-pdf" not in normalized
    assert "torch" not in normalized
    assert "torchvision" not in normalized
    assert "torchaudio" not in normalized
    assert "faiss-gpu" not in normalized


def test_dockerfile_installs_java_without_gpu_heavy_runtime_packages() -> None:
    src = (ROOT / "Dockerfile").read_text(encoding="utf-8").lower()

    assert "default-jre-headless" in src
    assert "download.pytorch.org" not in src
    assert "torch" not in src
    assert "torchvision" not in src
    assert "easyocr" not in src
    assert "onnxruntime" not in src


def test_requirements_use_docling_slim_without_standard_heavy_extra() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    normalized = {
        line.strip().split("==", 1)[0].split(">=", 1)[0].lower()
        for line in requirements
        if line.strip() and not line.strip().startswith("#")
    }

    assert "docling-slim" in normalized
    assert "docling-parse" in normalized
    assert "pypdfium2" in normalized
    assert "docling" not in normalized


def test_agents_boundary_does_not_expose_private_host_path() -> None:
    src = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    private_host_user = "ec2" + "-" + "user"
    private_host_path = "/" + "home" + "/" + private_host_user

    assert private_host_user not in src
    assert private_host_path not in src
