"""Cross-layer contracts that must remain aligned during future updates."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app_v2 import create_app
from backend.config import ATTACHMENT_CATEGORIES
from backend.services.attachment_service import DEFAULT_ALLOWED_CATEGORIES
from backend.services.lead_service import STAGE_ORDER


ROOT = Path(__file__).parent


def test_sales_stage_contract() -> None:
    fields = json.loads((ROOT / "config" / "fields.json").read_text(encoding="utf-8"))
    configured = fields["field_groups"]["evaluation"]["fields"]["stage"]["options"]
    expected = list(STAGE_ORDER)
    assert configured == expected, f"stage mismatch: config={configured}, backend={expected}"


def test_attachment_category_contract() -> None:
    schema = (ROOT / "backend" / "schema.sql").read_text(encoding="utf-8")
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS attachments.*?category TEXT NOT NULL CHECK\s*"
        r"\(\s*category IN \(([^)]+)\)",
        schema,
        re.DOTALL,
    )
    assert match, "attachment category constraint not found in schema"
    schema_categories = tuple(re.findall(r"'([^']+)'", match.group(1)))

    files_view = (ROOT / "frontend" / "js" / "modules" / "files-view.js").read_text(encoding="utf-8")
    ui_block = re.search(r"const categories = \[(.*?)\n\s*\];", files_view, re.DOTALL)
    assert ui_block, "attachment category list not found in frontend"
    ui_categories = tuple(re.findall(r"value: '([^']+)'", ui_block.group(1)))

    expected = tuple(ATTACHMENT_CATEGORIES)
    assert tuple(DEFAULT_ALLOWED_CATEGORIES) == expected
    assert schema_categories == expected
    assert ui_categories == expected


def test_config_single_source_and_routes() -> None:
    duplicate_configs = list((ROOT / "frontend" / "config").glob("*.json"))
    assert not duplicate_configs, f"duplicate frontend configs remain: {duplicate_configs}"

    app_js = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
    for name in ("fields", "products", "regions"):
        assert (ROOT / "config" / f"{name}.json").is_file()
        assert f"/api/config/{name}" in app_js
        assert f"/static/config/{name}.json" not in app_js

    app = create_app()
    routes = {
        (method, route.path)
        for route in app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    for name in ("fields", "products", "regions"):
        assert ("GET", f"/api/config/{name}") in routes
    assert ("GET", "/api/health") in routes

    legacy_routes = {
        ("GET", "/api/config/user"),
        ("POST", "/api/config/user"),
        ("POST", "/api/logout"),
        ("POST", "/api/parse-email"),
    }
    assert routes.isdisjoint(legacy_routes)

    with tempfile.TemporaryDirectory() as data_dir:
        with patch.dict(os.environ, {"JPT_DATA_DIR": data_dir}):
            with TestClient(create_app()) as client:
                for name in ("fields", "products", "regions"):
                    response = client.get(f"/api/config/{name}")
                    assert response.status_code == 200
                assert client.get("/api/health").json()["status"] == "ok"
                assert client.get("/api/config/user").status_code == 404


def test_confirmed_dead_files_are_removed() -> None:
    removed = [
        "backend/app.py",
        "backend/database.py",
        "backend/models.py",
        "frontend/js/modules/dashboard.js",
        "frontend/js/modules/coordinate-review.js",
        "frontend/js/modules/lead-panel.js",
        "frontend/js/shared/dom.js",
    ]
    remaining = [path for path in removed if (ROOT / path).exists()]
    assert not remaining, f"confirmed dead files remain: {remaining}"


def main() -> None:
    tests = [
        test_sales_stage_contract,
        test_attachment_category_contract,
        test_config_single_source_and_routes,
        test_confirmed_dead_files_are_removed,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    print("PASS: runtime contract validation completed")


if __name__ == "__main__":
    main()
