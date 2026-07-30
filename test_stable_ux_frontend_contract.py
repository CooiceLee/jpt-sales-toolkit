#!/usr/bin/env python3
"""Stable-release UX and accessibility contracts."""

from pathlib import Path


ROOT = Path(__file__).parent


def main() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    utils = (ROOT / "frontend" / "js" / "shared" / "utils.js").read_text(
        encoding="utf-8"
    )
    trip_plans = (
        ROOT / "frontend" / "js" / "modules" / "trip-plans.js"
    ).read_text(encoding="utf-8")
    trip_visits = (
        ROOT / "frontend" / "js" / "modules" / "trip-visit-actions.js"
    ).read_text(encoding="utf-8")
    user_menu = (
        ROOT / "frontend" / "js" / "modules" / "user-menu.js"
    ).read_text(encoding="utf-8")

    for modal_id, title_id in (
        ("login-modal", "login-modal-title"),
        ("activation-modal", "activation-modal-title"),
        ("coordinate-modal", "coordinate-modal-title"),
    ):
        marker = f'id="{modal_id}"'
        declaration = index[index.index(marker):index.index(marker) + 180]
        assert 'role="dialog"' in declaration
        assert 'aria-modal="true"' in declaration
        assert f'aria-labelledby="{title_id}"' in declaration

    assert 'id="login-error" role="alert" aria-live="assertive"' in index
    assert index.count('role="menuitem"') >= 3
    assert 'id="user-footer" role="button" tabindex="0"' in index
    assert 'id="user-menu" role="menu"' in index
    assert 'id="dashboard-status"' in index and 'aria-live="polite"' in index
    assert 'id="json-import-btn"' in index and "disabled" in index[
        index.index('id="json-import-btn"'):index.index('id="json-import-btn"') + 180
    ]

    assert "modalFocusOrigins" in utils
    assert "app.inert = true" in utils and "app.inert = false" in utils
    assert "event.key !== 'Tab'" in utils

    assert "window.archiveTripPlan" in trip_plans
    assert "ApiClient.archiveTripPlan(planId, rowVersion)" in trip_plans
    assert 'class="trip-plan-archive"' in trip_plans
    assert "files.slice(uploaded)" in trip_visits
    assert "if (input) input.value = ''" in trip_visits
    assert user_menu.count("PanelDirtyState.confirmDiscard()") >= 3

    print("PASS: stable UX, modal accessibility, archive and retry contracts")


if __name__ == "__main__":
    main()
