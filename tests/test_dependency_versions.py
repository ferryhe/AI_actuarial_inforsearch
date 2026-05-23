from pathlib import Path

from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]


def test_mistralai_is_pinned_to_supported_version() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pins = [line for line in requirements if line.startswith("mistralai==")]

    assert len(pins) == 1
    version = pins[0].split("==", 1)[1]
    assert Version(version) >= Version("1.12.4")
    assert "mistralai==1.0.0" not in requirements
