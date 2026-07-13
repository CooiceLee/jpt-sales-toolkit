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
    ):
        assert contract in all_modules, f"missing browser contract: {contract}"

    card_source = (MODULES / "card-template.js").read_text(encoding="utf-8")
    parser_source = (MODULES / "intake-parser.js").read_text(encoding="utf-8")
    assert "data-inquiry-card" in card_source and 'onclick="openInquiryPanel' not in card_source
    assert 'value="${escapeHtml(value || \'\')}"' in parser_source
    print("PASS: frontend module loading, size, browser API and escaping contracts")


if __name__ == "__main__":
    main()
