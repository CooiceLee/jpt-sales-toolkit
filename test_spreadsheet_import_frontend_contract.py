#!/usr/bin/env python3
"""Static contract for correction-first spreadsheet import controls."""

from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def main() -> None:
    view = (MODULES / "spreadsheet-import-view.js").read_text(encoding="utf-8")
    state = (MODULES / "spreadsheet-import-state.js").read_text(encoding="utf-8")
    actions = (MODULES / "spreadsheet-import-actions.js").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    roles = (MODULES / "role-capabilities.js").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    assert "item.entity_type !== 'member'" in view
    assert "source_record_key" in view and "data-exclude-key" in view
    assert "candidateOptions" in view and "selectedAvailable" in view
    assert "dirty" in state and "sourceHash" in state and "canCommit" in state
    assert "requireSpreadsheetLeader" in actions and "expected_source_hash" in api
    assert "report.quality_issue_count" in actions
    assert "canImportSpreadsheet" in roles and "data-leader-spreadsheet" in index
    assert "distributed separately from the application installer" in index
    assert "downloadImportTemplate" not in api
    assert "downloadStandardImportTemplate" not in actions
    for filename in (
        "spreadsheet-import-view.js", "spreadsheet-import-state.js",
        "spreadsheet-import-actions.js",
    ):
        lines = (MODULES / filename).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 125, f"{filename} exceeds the 125-line module boundary"
    print("PASS: spreadsheet mapping, exclusion, hash gate, and module-size contracts")


if __name__ == "__main__":
    main()
