"""Runtime and static contracts for planned-date and activity-age follow-up filters."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def main() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    worklist = (ROOT / "frontend" / "js" / "modules" / "sales-worklists.js").read_text(
        encoding="utf-8"
    )
    card = (ROOT / "frontend" / "js" / "modules" / "card-template.js").read_text(
        encoding="utf-8"
    )
    stage_filters = (
        ROOT / "frontend" / "js" / "modules" / "stage-filters.js"
    ).read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")

    for element_id in (
        "followup-activity-filter",
        "followup-activity-from",
        "followup-activity-to",
        "followup-custom-dates",
    ):
        assert f'id="{element_id}"' in index
    assert index.index("followup-filter-model.js") < index.index("sales-worklists.js")
    assert "Next 7 days" in index and "This week" not in index
    assert "window.FollowupFilterControls?.init()" in stage_filters
    assert "...getSharedLeadFilters()" in worklist
    assert "limit: 100000" in worklist
    assert "['Assigned', 'Following']" in worklist
    assert "missing a next follow-up date" in worklist
    assert "latest_follow_up_at: lead.latest_follow_up_at" in worklist
    assert "activity_age_days" in card and "Latest follow-up" in card
    for label in (
        "Any activity time",
        "Never formally followed up",
        "Inactive 90+ days",
        "Custom activity dates",
        "{count} days since inquiry (no formal follow-up)",
        "{shown} of {total} active",
    ):
        assert f"'{label}'" in i18n, f"missing translation: {label}"

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = { console, Date };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/followup-filter-model.js', 'utf8'), context);
const model = context.FollowupFilterModel;
const now = new Date(2026, 6, 20, 12);
const rows = model.annotate([
  { id: 'a', latest_follow_up_at: '2026-07-01T09:00:00', inquiry_date: '2026-01-01', created_at: '2026-01-01', next_followup_date: '2026-07-19' },
  { id: 'b', latest_follow_up_at: null, inquiry_date: '2026-07-10', created_at: '2026-01-01', next_followup_date: null },
  { id: 'c', latest_follow_up_at: '2026-07-18', inquiry_date: '2026-01-01', created_at: '2026-01-01', next_followup_date: '2026-07-20' },
  { id: 'd', latest_follow_up_at: null, inquiry_date: 'bad-date', created_at: '2026-04-01', next_followup_date: '2026-07-26' },
  { id: 'e', latest_follow_up_at: '2026-07-13', inquiry_date: '2026-01-01', created_at: '2026-01-01', next_followup_date: '2026-07-27' },
  { id: 'f', latest_follow_up_at: '2026-07-12', inquiry_date: '2026-01-01', created_at: '2026-01-01', next_followup_date: '2026-07-28' },
], now);
const ids = values => Array.from(values, item => item.id);
assert.deepStrictEqual(ids(model.filterPlanned(rows, 'overdue', now)), ['a']);
assert.deepStrictEqual(ids(model.filterPlanned(rows, 'today', now)), ['c']);
assert.deepStrictEqual(ids(model.filterPlanned(rows, 'week', now)), ['c', 'd']);
assert.deepStrictEqual(ids(model.filterActivity(rows, { mode: 'never' }, now)), ['b', 'd']);
assert.deepStrictEqual(ids(model.filterActivity(rows, { mode: '7' }, now)), ['a', 'b', 'd', 'e', 'f']);
assert.deepStrictEqual(ids(model.filterActivity(rows, {
  mode: 'custom', from: '2026-07-10', to: '2026-07-13'
}, now)), ['b', 'e', 'f']);
assert.deepStrictEqual(ids(model.filterActivity(rows, { mode: 'custom' }, now)), []);
assert.strictEqual(model.customRangeStatus({ from: '2026-07-14', to: '2026-07-13' }).reason, 'reversed');
assert.strictEqual(rows[0].activity_date_source, 'follow_up');
assert.strictEqual(rows[0].activity_age_days, 19);
assert.strictEqual(rows[1].activity_date_source, 'inquiry');
assert.strictEqual(rows[3].activity_date_source, 'created');
assert.strictEqual(model.sortOldestActivity(rows)[0].id, 'd');
const dstRow = model.annotate([
  { id: 'dst', latest_follow_up_at: '2026-03-08', inquiry_date: '2026-01-01' }
], new Date(2026, 2, 9, 12))[0];
assert.strictEqual(dstRow.activity_age_days, 1);

function control(value = '') {
  const handlers = {};
  return {
    value, handlers, dataset: {}, attributes: {},
    classList: { hidden: true, toggle(name, enabled) { if (name === 'hidden') this.hidden = enabled; } },
    addEventListener(type, listener) { handlers[type] = listener; },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}
const controls = {
  'followup-activity-filter': control('all'),
  'followup-activity-from': control(''),
  'followup-activity-to': control(''),
  'followup-custom-dates': control(),
};
let reloads = 0;
context.document = { getElementById: id => controls[id] || null };
context.loadFollowup = () => { reloads += 1; };
vm.runInContext(fs.readFileSync('frontend/js/modules/followup-filter-controls.js', 'utf8'), context);
context.FollowupFilterControls.init();
assert.strictEqual(controls['followup-activity-filter'].dataset.bound, '1');
assert.strictEqual(controls['followup-custom-dates'].classList.hidden, true);
controls['followup-activity-filter'].value = 'custom';
controls['followup-activity-filter'].handlers.change();
assert.strictEqual(controls['followup-custom-dates'].classList.hidden, false);
assert.strictEqual(reloads, 1);
controls['followup-activity-from'].handlers.change();
assert.strictEqual(reloads, 2);

context.escapeHtml = value => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
context.formatDate = value => String(value || '-');
context.I18n = { t: (text, params = {}) => text.replace(/\{(\w+)\}/g, (_, key) => params[key]) };
vm.runInContext(fs.readFileSync('frontend/js/modules/card-template.js', 'utf8'), context);
const html = context.renderInquiryCard({
  id: 'b', inquiry_id: 'JPT-B', company_name: 'B', stage: 'Following',
  follow_ups_count: 0, latest_follow_up_at: null, next_followup_date: null,
  activity_age_days: 10, activity_date_source: 'inquiry'
}, 'followup');
assert(html.includes('No formal follow-up'));
assert(html.includes('10 days since inquiry'));
assert(html.includes('Next follow-up'));
const formalHtml = context.renderInquiryCard({
  id: 'a', inquiry_id: 'JPT-A', company_name: 'A', stage: 'Following',
  follow_ups_count: 1, latest_follow_up_at: '2026-07-01',
  next_followup_date: '2026-07-19', activity_age_days: 19,
  activity_date_source: 'follow_up'
}, 'followup');
assert(formalHtml.includes('2026-07-01'));
assert(formalHtml.includes('19 days inactive'));

let requestedParams = null;
context.ApiClient = {
  listLeads: async params => {
    requestedParams = params;
    return Array.from({ length: 1101 }, (_, index) => ({
      id: `lead-${index}`, display_id: `JPT-${index}`, sales_stage: 'Following',
      customer: { display_name: `Customer ${index}` }, assignments: [],
      inquiry_date: '2025-01-01', created_at: '2025-01-01',
      latest_follow_up_at: '2025-01-01', next_followup_date: null,
    }));
  },
};
context.getSharedLeadFilters = () => ({ business_region: 'EU' });
context.State = {
  currentFilters: { followup: 'all' },
  stageFilters: { search: '', customerId: '', ownerId: '', techId: '', businessRegion: 'EU' },
  user: { id: 'leader', role: 'leader' },
};
context.FollowupFilterControls = { read: () => ({ mode: '90', from: '', to: '' }) };
context.getLeadPrimaryContact = () => null;
context.setText = () => {};
context.syncStageFilterInputs = () => {};
context.switchModule = () => {};
context.loadModuleData = async () => {};
context.openInquiryPanel = async () => {};
context.renderCards = (containerId, items) => {
  assert.strictEqual(containerId, 'followup-cards');
  assert.strictEqual(items.length, 1101);
};
vm.runInContext(fs.readFileSync('frontend/js/modules/lead-navigation.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/sales-worklists.js', 'utf8'), context);
(async () => {
  await context.loadFollowup();
  assert.strictEqual(requestedParams.business_region, 'EU');
  assert.ok(requestedParams.limit > 1000);
  await context.jumpToCustomerStageCards('', 'Following', 'customer-1');
  assert.strictEqual(context.State.stageFilters.customerId, 'customer-1');
  assert.strictEqual(context.State.stageFilters.businessRegion, '');
})().catch(error => { console.error(error); process.exit(1); });
"""
    subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        check=True,
        env={**os.environ, "TZ": "America/New_York"},
    )
    print("PASS: planned-date and long-unfollowed frontend filter contracts")


if __name__ == "__main__":
    main()
