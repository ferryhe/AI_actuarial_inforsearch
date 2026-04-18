from __future__ import annotations

from ai_actuarial.api.app import create_app


def test_fastapi_runtime_boundary_no_longer_depends_on_flask_inventory() -> None:
    app = create_app()
    assert not hasattr(app.state, "legacy_flask_app")
    assert not hasattr(app.state, "legacy_flask_only_signatures")
