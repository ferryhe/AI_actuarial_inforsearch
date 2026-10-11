from __future__ import annotations

from pathlib import Path

from ai_actuarial.api.app import create_app
from tests.postgres_helpers import postgres_url_for_path


def test_fastapi_runtime_boundary_no_longer_depends_on_flask_inventory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url_for_path(tmp_path / "app.db"))
    app = create_app()
    assert not hasattr(app.state, "legacy_flask_app")
    assert not hasattr(app.state, "legacy_flask_only_signatures")
