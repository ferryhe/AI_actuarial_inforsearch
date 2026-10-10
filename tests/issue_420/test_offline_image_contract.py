"""Guard the command contract used for the Issue #420 image acceptance probe."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_offline_smoke_overrides_the_api_entrypoint_and_runs_packaged_probe():
    dockerfile = (ROOT / "Dockerfile").read_text()
    smoke = (ROOT / "tests/issue_420/smoke.sh").read_text()

    assert "COPY ./tests /app/tests" in dockerfile
    assert "--network none" in smoke
    assert "--entrypoint python" in smoke
    assert 'image="${1:-issue420-image:v2}"' in smoke
    assert "/app/tests/issue_420/offline_tokenizer_smoke.py" in smoke
    assert "docker rm" not in smoke
    assert "--name issue420-test" not in smoke


def test_offline_probe_covers_the_same_tokenizers_warmed_by_the_image():
    dockerfile = (ROOT / "Dockerfile").read_text()
    probe = (ROOT / "tests/issue_420/offline_tokenizer_smoke.py").read_text()

    for tokenizer in (
        "cl100k_base",
        "p50k_base",
        "p50k_edit",
        "o200k_base",
        "o200k_harmony",
        "gpt2",
        "r50k_base",
        "gpt-4",
        "gpt-4o",
        "gpt-4.1",
        "gpt-5",
        "o1",
        "o3",
        "o4-mini",
        "text-embedding-3-large",
        "text-embedding-3-small",
        "text-embedding-ada-002",
    ):
        assert tokenizer in dockerfile
        assert tokenizer in probe
