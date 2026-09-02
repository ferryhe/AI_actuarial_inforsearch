from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_databases_are_ignored():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "config/*.db" in gitignore
    assert "*.sqlite" in gitignore
    assert "*.sqlite3" in gitignore
