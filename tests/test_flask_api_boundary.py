from __future__ import annotations

import json
from pathlib import Path

from ai_actuarial.api.app import create_app


def test_legacy_flask_api_surface_is_frozen_to_baseline() -> None:
    app = create_app()
    legacy_app = app.state.legacy_flask_app
    assert legacy_app is not None

    baseline_path = Path(__file__).parent / "fixtures" / "flask_api_route_signatures.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    current_signatures = app.state.legacy_flask_only_signatures

    assert current_signatures == baseline["route_signatures"]
