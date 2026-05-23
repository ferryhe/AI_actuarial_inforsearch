from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mistralai_is_pinned_to_current_supported_version() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "mistralai==1.12.4" in requirements
    assert "mistralai==1.0.0" not in requirements
