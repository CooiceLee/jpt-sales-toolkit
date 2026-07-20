#!/usr/bin/env python3
"""Runtime contract for fuzzy merge selection, preview gate and UI refresh."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def main() -> None:
    index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    api = (ROOT / "frontend/js/api-client.js").read_text(encoding="utf-8")
    preview = (ROOT / "frontend/js/modules/customer-merge-preview.js").read_text(encoding="utf-8")
    conflict_view = (
        ROOT / "frontend/js/modules/customer-merge-conflict-view.js"
    ).read_text(encoding="utf-8")
    action = (ROOT / "frontend/js/modules/customer-merge-action.js").read_text(encoding="utf-8")
    view = (ROOT / "frontend/js/modules/customer-merge-view.js").read_text(encoding="utf-8")

    assert 'id="customer-merge-confirm"' in index and "disabled" in index
    assert "/customers/merge/candidates" in api
    assert "/customers/merge/preview" in api
    assert "listCustomerMergeCandidates" in view
    assert "CustomerMergePreview.matches()" in action
    assert "refreshAllCounts()" in action
    assert "refreshCurrentInquiryData" in action
    assert index.index("customer-merge-conflict-view.js") < index.index("customer-merge-preview.js")
    assert "Field conflicts" in conflict_view and "Source value" in conflict_view
    assert "merge-conflict-list" in conflict_view
    assert "searchSequence" in view and "selectionSequence" in view

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const elements = new Map(['customer-merge-confirm','customer-merge-preview','customer-merge-result']
    .map(id => [id, { id, innerHTML: '', textContent: '', disabled: false }]));
let previews = 0, merges = 0, refreshes = 0, notices = 0;
const context = {
    console,
    State: {
        user: { role: 'leader' }, currentInquiry: null, inquiries: [1],
        customerMerge: {
            source: { id: 'source', row_version: 2, display_name: 'Source' },
            target: { id: 'target', row_version: 3, display_name: 'Target' },
            preview: null,
        },
    },
    document: { getElementById: id => elements.get(id) || null },
    ApiClient: {
        previewCustomerMerge: async payload => {
            previews += 1;
            assert.strictEqual(payload.source_row_version, 2);
            return {
                counts: { leads: 2, contacts: 1, aliases: 1 },
                field_conflicts: [{
                    field: 'country', source: '<Source Country>', target: 'Target Country',
                    resolution: 'keep_target',
                }],
                contact_conflicts: [], domain_conflicts: [], alias_conflicts: [],
            };
        },
        mergeCustomers: async payload => {
            merges += 1;
            assert.ok(previews > 0);
            assert.strictEqual(payload.target_row_version, 3);
            return { moved_leads: 2, moved_contacts: 1, moved_aliases: 1, moved_domains: 0 };
        },
    },
    CustomerMergeView: { clear() {} },
    I18n: { t: (text, params = {}) => Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text) },
    escapeHtml: value => String(value).replace(/&/g, '&amp;')
        .replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
    confirm: () => true,
    notify: () => { notices += 1; },
    refreshAllCounts: async () => { refreshes += 1; },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/customer-merge-conflict-view.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/customer-merge-preview.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/customer-merge-action.js', 'utf8'), context);
(async () => {
    await context.mergeSelectedCustomers();
    assert.strictEqual(previews, 1);
    assert.strictEqual(merges, 0);
    assert.strictEqual(elements.get('customer-merge-confirm').disabled, false);
    assert.ok(elements.get('customer-merge-preview').innerHTML.includes('&lt;Source Country&gt;'));
    assert.ok(elements.get('customer-merge-preview').innerHTML.includes('Keep target value'));
    await context.mergeSelectedCustomers();
    assert.strictEqual(merges, 1);
    assert.strictEqual(refreshes, 1);
    assert.strictEqual(notices, 1);
    assert.strictEqual(context.State.inquiries.length, 0);
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: fuzzy customer merge requires preview and refreshes related UI")


if __name__ == "__main__":
    main()
