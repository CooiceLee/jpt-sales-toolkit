"""Frontend contract for recipient-scoped JSON export."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def main() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    client = (ROOT / "frontend" / "js" / "api-client.js").read_text(encoding="utf-8")
    assert 'id="json-export-recipient"' in index
    assert index.index("json-export.js") < index.index("data-transfer.js")
    assert "recipient_user_id: recipientUserId" in client

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const elements = {
  'json-export-recipient-field': { hidden: true },
  'json-export-recipient': { value: '', innerHTML: '' },
  'export-result': { style: {}, className: '', textContent: '' }
};
let exportRecipient = 'unset';
let alertText = '';
const context = {
  console,
  State: { user: { role: 'leader' } },
  I18n: { t: value => value },
  escapeHtml: value => String(value),
  alert: value => { alertText = value; },
  ApiClient: {
    listUsers: async role => role === 'sales'
      ? [{ id: 'sales-a', display_name: 'Sales A' }] : [],
    exportData: async (_ids, recipient) => {
      exportRecipient = recipient;
      return { blob: {}, filename: 'package.json' };
    }
  },
  URL: { createObjectURL: () => 'blob:test', revokeObjectURL: () => {} },
  document: {
    getElementById: id => elements[id],
    createElement: () => ({ click() {}, remove() {} }),
    body: { appendChild() {} }
  }
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(
  'frontend/js/modules/json-export.js', 'utf8'
), context);
(async () => {
  await context.JsonExport.ensureRecipients();
  assert.strictEqual(elements['json-export-recipient-field'].hidden, false);
  assert.ok(elements['json-export-recipient'].innerHTML.includes('sales-a'));
  await context.exportData();
  assert.ok(alertText.includes('select a recipient'));
  assert.strictEqual(exportRecipient, 'unset');
  elements['json-export-recipient'].value = 'sales-a';
  await context.exportData();
  assert.strictEqual(exportRecipient, 'sales-a');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    test_json_import_gate()
    print("PASS: JSON export recipient and guarded import frontend contracts")


def test_json_import_gate() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const fileA = { name: 'a.json', size: 100, lastModified: 1 };
const fileB = { name: 'b.json', size: 100, lastModified: 2 };
const listeners = {};
const elements = {
  'json-import-file': {
    files: [fileA], value: 'a.json', dataset: {},
    addEventListener(type, handler) { listeners[type] = handler; }
  },
  'json-preflight-result': { innerHTML: '' },
  'json-import-result': { innerHTML: '' },
  'json-import-btn': {
    disabled: false, title: '', attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; }
  }
};
let preflightReport = {
  source_snapshot: { leads: 10 },
  permission: { allowed_leads: 9, skipped_leads: 1 },
  summary: { errors: 0, warnings: 0, duplicates: 0 },
  issues: [], duplicates: []
};
let importCalls = 0;
let importReport = {
  total_records: 2, new_customers: 0, updated_customers: 1,
  new_leads: 0, updated_leads: 1, skipped_records: 1, errors: []
};
const context = {
  console,
  State: { user: { role: 'sales' } },
  I18n: { t: value => value },
  escapeHtml: value => String(value),
  renderPreflightIssueList: (title, values) => `${title}:${values.join('|')}`,
  alert() {},
  refreshAllCounts: async () => {},
  ApiClient: {
    preflightImportData: async () => preflightReport,
    importData: async () => { importCalls += 1; return importReport; },
    createFullBackup: async () => ({})
  },
  document: {
    readyState: 'complete',
    getElementById: id => elements[id] || null,
    querySelector: () => null
  }
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(
  'frontend/js/modules/data-transfer-view.js', 'utf8'
), context);
vm.runInContext(fs.readFileSync(
  'frontend/js/modules/data-transfer.js', 'utf8'
), context);
(async () => {
  assert.strictEqual(elements['json-import-btn'].disabled, true);
  await context.importJsonData();
  assert.strictEqual(importCalls, 0);

  await context.preflightJsonImport();
  assert.strictEqual(elements['json-import-btn'].disabled, true);
  assert.ok(elements['json-preflight-result'].innerHTML.includes('10'));
  assert.ok(elements['json-preflight-result'].innerHTML.includes('Skipped'));

  preflightReport = {
    source_snapshot: { leads: 10 },
    permission: { allowed_leads: 10, skipped_leads: 0 },
    summary: { errors: 1, warnings: 0, duplicates: 0 },
    issues: [{ severity: 'error', entity: 'lead:1', message: 'bad' }],
    duplicates: []
  };
  await context.preflightJsonImport();
  assert.strictEqual(elements['json-import-btn'].disabled, true);

  preflightReport = {
    source_snapshot: { leads: 10 },
    permission: { allowed_leads: 10, skipped_leads: 0 },
    summary: { errors: 0, warnings: 1, duplicates: 0 },
    issues: [], duplicates: []
  };
  await context.preflightJsonImport();
  assert.strictEqual(elements['json-import-btn'].disabled, false);

  elements['json-import-file'].files = [fileB];
  listeners.change();
  assert.strictEqual(elements['json-import-btn'].disabled, true);
  await context.importJsonData();
  assert.strictEqual(importCalls, 0);

  await context.preflightJsonImport();
  assert.strictEqual(elements['json-import-btn'].disabled, false);
  await context.importJsonData();
  assert.strictEqual(importCalls, 1);
  assert.ok(elements['json-import-result'].innerHTML.includes('data-import-outcome="partial"'));
  assert.strictEqual(elements['json-import-btn'].disabled, true);

  context.LegacyImportView.renderImport({
    total_records: 1, new_leads: 0, updated_leads: 0,
    skipped_records: 1, errors: ['bad']
  });
  assert.ok(elements['json-import-result'].innerHTML.includes('data-import-outcome="failed"'));
  context.LegacyImportView.renderImport({
    total_records: 1, new_leads: 1, updated_leads: 0,
    skipped_records: 0, errors: []
  });
  assert.ok(elements['json-import-result'].innerHTML.includes('data-import-outcome="success"'));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


if __name__ == "__main__":
    main()
