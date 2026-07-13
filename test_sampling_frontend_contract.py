"""Static contracts for the modular Sampling frontend and task API."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app_v2 import create_app


ROOT = Path(__file__).parent


def main() -> None:
    fields = json.loads((ROOT / "config" / "fields.json").read_text(encoding="utf-8"))
    assert "sample" not in fields["field_groups"]

    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    scripts = ["sampling-panel.js", "sampling-actions.js", "sampling.js"]
    positions = [index.index(script) for script in scripts]
    assert positions == sorted(positions)
    for task_status in ("Open", "In Progress", "Completed", "Cancelled"):
        assert f'data-filter="{task_status}"' in index

    app_js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    inquiry_form_js = (ROOT / "frontend" / "js" / "modules" / "inquiry-form.js").read_text(encoding="utf-8")
    api_js = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    assert "async function loadSampling" not in app_js
    assert "SamplingModule.renderTab" in inquiry_form_js
    for method in ("updatePreSalesTask", "archivePreSalesTask", "restorePreSalesTask"):
        assert method in api_js

    routes = {
        (method, route.path)
        for route in create_app().routes
        for method in (getattr(route, "methods", None) or set())
    }
    expected = {
        ("PATCH", "/api/pre-sales-tasks/{task_id}"),
        ("POST", "/api/pre-sales-tasks/{task_id}/archive"),
        ("POST", "/api/pre-sales-tasks/{task_id}/restore"),
    }
    assert expected <= routes
    print("PASS: Sampling frontend modules and task API contracts")


if __name__ == "__main__":
    main()
