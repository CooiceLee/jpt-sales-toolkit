"""Static contracts for the classic-script frontend module boundary."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
MODULES = FRONTEND / "js" / "modules"


def main() -> None:
    index = (FRONTEND / "index.html").read_text(encoding="utf-8")
    app_source = (FRONTEND / "js" / "app.js").read_text(encoding="utf-8")
    script_sources = re.findall(r'<script\s+src="([^"]+\.js)(?:\?[^" ]*)?"', index)

    assert len(script_sources) == len(set(script_sources)), "duplicate script include found"
    local_sources = [source for source in script_sources if source.startswith("/static/js/")]
    for source in local_sources:
        assert (FRONTEND / source.removeprefix("/static/")).is_file(), f"missing script: {source}"

    module_sources = {f"/static/js/modules/{path.name}" for path in MODULES.glob("*.js")}
    assert module_sources <= set(script_sources), "one or more frontend modules are not loaded"
    assert script_sources.index("/static/js/shared/utils.js") < script_sources.index("/static/js/app.js")
    assert script_sources.index("/static/js/app.js") < script_sources.index("/static/js/modules/intake-parser.js")
    assert script_sources.index("/static/js/modules/authorization-model.js") < script_sources.index(
        "/static/js/modules/authorization-activation.js"
    )
    assert script_sources.index("/static/js/modules/authorization-center.js") < script_sources.index(
        "/static/js/modules/authorization-center-view.js"
    )
    sort_module = "/static/js/modules/worklist-sort.js"
    for worklist in (
        "/static/js/modules/sales-worklists.js",
        "/static/js/modules/service-worklists.js",
        "/static/js/modules/sampling.js",
    ):
        assert script_sources.index(sort_module) < script_sources.index(worklist)
    coordinate_modules = [
        "/static/js/modules/coordinate-state.js",
        "/static/js/modules/coordinate-fields.js",
        "/static/js/modules/coordinate-geocode-view.js",
        "/static/js/modules/coordinate-panel.js",
        "/static/js/modules/coordinate-actions.js",
        "/static/js/modules/coordinate-save.js",
    ]
    assert [script_sources.index(source) for source in coordinate_modules] == sorted(
        script_sources.index(source) for source in coordinate_modules
    ), "coordinate modules must preserve state/view/action dependency order"
    for source in coordinate_modules:
        lines = (FRONTEND / source.removeprefix("/static/")).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 125, f"coordinate module boundary exceeded: {source}"

    assert len(app_source.splitlines()) <= 600, "app.js has grown beyond its entry-file boundary"
    for extracted_marker in (
        "Parser", "Detail Panel", "Follow-ups Tab", "Export/Import",
        "Trip Planner", "Coordinate Correction", "Coordinate Review Module",
    ):
        assert f"// ===== {extracted_marker}" not in app_source

    oversized = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in MODULES.glob("*.js")
        if len(path.read_text(encoding="utf-8").splitlines()) > 160
    }
    assert not oversized, f"module boundary exceeded: {oversized}"

    all_modules = "\n".join(path.read_text(encoding="utf-8") for path in MODULES.glob("*.js"))
    for contract in (
        "window.initParser", "window.loadHandler", "window.renderCards",
        "window.openInquiryPanel", "window.saveInquiry", "window.loadTripPlanner",
        "window.openCoordinateCorrection", "window.loadDataReview",
        "window.initAuthorizationActivation", "window.loadAuthorizationCenter",
        "window.saveAuthorizationMember", "window.issueMemberAuthorization",
    ):
        assert contract in all_modules, f"missing browser contract: {contract}"

    api_source = (FRONTEND / "js" / "api-client.js").read_text(encoding="utf-8")
    for endpoint in (
        "/authorization/status", "/authorization/device-request", "/authorization/activate",
        "/authorization/members", "/authorization/issuer/initialize",
        "/authorization/issue", "/authorization/events",
        "/health", "/desktop/shutdown",
    ):
        assert endpoint in api_source, f"missing authorization API endpoint: {endpoint}"

    for element_id in (
        "activation-modal", "activation-file", "activation-password",
        "module-authorization", "authorization-member-role", "authorization-request-file",
    ):
        assert f'id="{element_id}"' in index, f"missing authorization UI element: {element_id}"

    button_tags = re.findall(r"<button\b[^>]*>", index, flags=re.IGNORECASE)
    assert all(re.search(r'\btype="button"', tag, flags=re.IGNORECASE) for tag in button_tags), (
        "every non-submit button must explicitly use type=button"
    )

    role_options = set(re.findall(r'<option value="(leader|sales|tech)">', index))
    assert role_options == {"leader", "sales", "tech"}, "authorization roles must stay Leader/Sales/Tech"

    capability_source = (MODULES / "role-capabilities.js").read_text(encoding="utf-8")
    sampling_actions = (MODULES / "sampling-actions.js").read_text(encoding="utf-8")
    sampling_form_data = (MODULES / "sampling-form-data.js").read_text(encoding="utf-8")
    aftersales_actions = (MODULES / "aftersales-actions.js").read_text(encoding="utf-8")
    assert "new Set(['sampling', 'aftersales'])" in capability_source
    assert "RoleCapabilities.isTech()" in sampling_actions
    assert "PreSalesTaskModel.mergeResult" in sampling_form_data
    assert "RoleCapabilities.isTech()" in aftersales_actions
    assert "desktop-exit" in index

    card_source = (MODULES / "card-template.js").read_text(encoding="utf-8")
    parser_source = (MODULES / "intake-parser.js").read_text(encoding="utf-8")
    assert "data-inquiry-card" in card_source and 'onclick="openInquiryPanel' not in card_source
    assert 'value="${escapeHtml(value || \'\')}"' in parser_source
    print("PASS: frontend module loading, size, browser API and escaping contracts")


if __name__ == "__main__":
    main()
