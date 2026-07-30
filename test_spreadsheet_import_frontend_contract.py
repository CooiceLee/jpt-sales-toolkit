#!/usr/bin/env python3
"""Static contract for correction-first spreadsheet import controls."""

from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def main() -> None:
    view = (MODULES / "spreadsheet-import-view.js").read_text(encoding="utf-8")
    state = (MODULES / "spreadsheet-import-state.js").read_text(encoding="utf-8")
    actions = (MODULES / "spreadsheet-import-actions.js").read_text(encoding="utf-8")
    progress = (MODULES / "spreadsheet-import-progress.js").read_text(encoding="utf-8")
    api = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    roles = (MODULES / "role-capabilities.js").read_text(encoding="utf-8")
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    regression = (ROOT / "frontend" / "regression.html").read_text(encoding="utf-8")

    assert "item.entity_type !== 'member'" in view
    assert "source_record_key" in view and "data-exclude-key" in view
    assert "candidateOptions" in view and "selectedAvailable" in view
    assert "item.mapping_key || name" in view and "data-member-key" in view
    assert "dirty" in state and "sourceHash" in state and "canCommit" in state
    assert "forceReset" in state and "useFile(file, true)" in actions
    assert "requireSpreadsheetLeader" in actions and "expected_source_hash" in api
    assert "error.report = detail?.report || payload?.report" in api
    assert "spreadsheetNetworkError" in api and "spreadsheetResponseError" in api
    assert "cache: 'no-store'" in api and "responseText = await response.text()" in api
    assert "Array.isArray(payload)" in api and "Invalid spreadsheet response" in api
    assert "local_service_unavailable" in api and "spreadsheet_request_failed" in api
    assert "spreadsheet_commit_outcome_unconfirmed" in api and "outcomeUnconfirmed" in api
    assert "The current workbook was not imported" in api
    assert "verify the navigation counts and target records" in api
    assert "Failed to fetch" not in actions and "SyntaxError" not in actions
    assert "SpreadsheetImportProgress.begin('preflight', file)" in actions
    assert "SpreadsheetImportProgress.isCurrent(ticket)" in actions
    assert "SpreadsheetImportProgress.finish(ticket)" in actions
    assert "requestNonce" in progress and "input.disabled = pickerDisabled" in progress
    assert "selectionEpoch" in progress and "ticket.file === file" in progress
    assert "markCommitUnconfirmed" in progress and "commitUnconfirmed" in progress
    assert "const canCommit = backupComplete && preflightReady" in progress
    assert "Create a full backup before import" in progress
    assert "isBackupComplete" in progress
    assert "selectionChanged" in actions and "error.outcomeUnconfirmed" in actions
    assert "refreshAllCounts().catch" in actions and "Import completed, but navigation counts" in actions
    assert "picker.setAttribute('aria-disabled'" in progress
    assert "当前工作簿尚未导入" in i18n and "本次导入结果无法确认" in i18n
    assert "mode === 'spreadsheet-network'" in regression
    assert "Spreadsheet actions were not locked during preflight" in regression
    assert "staleReportIgnored" in regression and "same-metadata.xlsx" in regression
    assert "pickerLockedAfterUnconfirmed" in regression
    assert "Workbook picker was not locked during preflight" in regression
    assert "Commit failure made an unsafe not-imported claim" in regression
    assert "report.quality_issue_count" in actions
    assert "error.report" in actions
    assert "canImportSpreadsheet" in roles and "data-leader-spreadsheet" in index
    assert 'data-transfer-target="spreadsheet"' in index
    assert 'data-transfer-target="json"' in index
    assert 'id="json-import-file"' in index
    assert 'id="import-preflight-result" class="import-preflight-scroll"' in index
    assert 'id="import-file" class="visually-hidden" accept=".xlsx' in index
    assert "downloadImportTemplate" not in api
    assert "downloadStandardImportTemplate" not in actions
    for filename in (
        "spreadsheet-import-view.js", "spreadsheet-import-state.js",
        "spreadsheet-import-actions.js", "spreadsheet-import-progress.js",
    ):
        lines = (MODULES / filename).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 125, f"{filename} exceeds the 125-line module boundary"
    print("PASS: spreadsheet mapping, exclusion, hash gate, and module-size contracts")


if __name__ == "__main__":
    main()
