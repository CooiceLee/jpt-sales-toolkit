"""Every "create" button starts the thing it names, from an empty queue.

"Create quote", "Log issue" and "New pre-sales task" switched module and asked
the reader to select a card - from lists that only held leads which already had
that kind of record. So the first quotation, the first pre-sales task and the
first after-sales issue could not be started from the button that offered them.

The picker searches the leads the reader may open, not the ones already
carrying the record being created, and then opens that lead's panel on the
right tab with the form up.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
assert 'id="action-picker-modal"' in INDEX, "the lead picker is not on the page"
assert 'for="action-picker-search"' in INDEX, "the search box has no label"
# An action that only updates an existing order must not read as a creation.
assert "+ Log status" not in INDEX
assert "Update fulfillment status" in INDEX
# After-sales creation is a task-manager action, like the pre-sales one.
issue_button = INDEX[INDEX.index('onclick="logIssue()"') - 200:INDEX.index('onclick="logIssue()"')]
assert "data-task-manager" in issue_button, (
    "the after-sales creation button is offered to accounts that cannot use it"
)

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function build({ leads = [], currentInquiry = null, role = 'leader',
                opens = true } = {}) {
  const elements = {
    'action-picker-title': { textContent: '' },
    'action-picker-search': { value: '' },
    'action-picker-results': { innerHTML: '' },
    'action-picker-status': { textContent: '' },
  };
  const seen = { shown: [], hidden: [], opened: [], forms: [], queries: [] };
  const context = {
    console,
    I18n: { t: (text, params = {}) =>
      String(text).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`) },
    escapeHtml: value => String(value ?? ''),
    State: { currentInquiry, user: { id: 'u1', role } },
    RoleCapabilities: { isTech: () => role === 'tech',
                        canManageTaskRequests: () => role !== 'tech' },
    document: { getElementById: id => elements[id] || null },
    showModal: id => seen.shown.push(id),
    hideModal: id => seen.hidden.push(id),
    // The real one reports whether the lead it was given is the one now on
    // screen. A stub that always succeeds hid a picker that ran its action on
    // whoever the reader had opened meanwhile.
    openInquiryPanel: async (id, context_) => {
      seen.opened.push([id, context_]);
      if (opens === false) return false;
      context.State.currentInquiry = { id };
      return true;
    },
    ApiClient: {
      listLeads: async params => {
        seen.queries.push(params);
        const offset = Number(params.offset) || 0;
        const limit = Number(params.limit) || leads.length;
        const term = String(params.search || '').toLowerCase();
        const matching = term
          ? leads.filter(lead => JSON.stringify(lead).toLowerCase().includes(term))
          : leads;
        return matching.slice(offset, offset + limit);
      },
    },
    showFollowUpForm: () => { seen.forms.push('followup'); },
    showSampleTaskForm: () => { seen.forms.push('sample'); },
    showAfterSalesForm: () => { seen.forms.push('aftersales'); },
    switchModule: () => { throw new Error('a create action switched module instead'); },
    notify: () => {},
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('frontend/js/modules/paged-fetch.js', 'utf8'), context);
  context.ApiClient.listAllLeads = params =>
    context.PagedFetch.all(page => context.ApiClient.listLeads({ ...params, ...page }));
  vm.runInContext(
    fs.readFileSync('frontend/js/modules/business-action-picker.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('frontend/js/modules/legacy-actions.js', 'utf8'), context);
  return { context, elements, seen };
}

// Leads that carry none of the records these buttons create: this is the state
// the buttons could not get out of.
const emptyQueue = [
  { id: 'lead-1', display_id: 'JPT-1', sales_stage: 'New',
    customer: { display_name: 'Erste Laser GmbH' }, title: 'Cutting head' },
  { id: 'lead-2', display_id: 'JPT-2', sales_stage: 'Following',
    customer: { display_name: 'Zweite Optik' }, title: 'Beam delivery' },
];

(async () => {
  for (const [action, context_, form] of [
    ['createQuote', 'deal', null],
    ['newSampleRequest', 'sampling', 'sample'],
    ['logIssue', 'aftersales', 'aftersales'],
    ['logFollowUp', 'followup', 'followup'],
  ]) {
    const app = build({ leads: emptyQueue });
    await app.context[action]();
    await new Promise(resolve => setImmediate(resolve));
    assert.deepStrictEqual(app.seen.shown, ['action-picker-modal'],
      `${action}: no picker appeared`);
    assert.ok(app.elements['action-picker-title'].textContent.length > 0,
      `${action}: the picker does not say what it is for`);
    // Every lead the reader may open is offered, not only those that already
    // carry this kind of record.
    assert.ok(app.elements['action-picker-results'].innerHTML.includes('JPT-1')
      && app.elements['action-picker-results'].innerHTML.includes('JPT-2'),
      `${action}: a lead with no such record yet was not offered`);
    assert.ok(app.seen.queries.every(query => !('sales_stage' in query)),
      `${action}: the search was narrowed to a stage: ${JSON.stringify(app.seen.queries)}`);

    await app.context.BusinessActionPicker.choose(0);
    assert.deepStrictEqual(app.seen.hidden, ['action-picker-modal']);
    assert.deepStrictEqual(app.seen.opened, [['lead-1', context_]],
      `${action}: opened the wrong lead or the wrong tab`);
    assert.deepStrictEqual(app.seen.forms, form ? [form] : [],
      `${action}: the form was not opened: ${app.seen.forms}`);
  }

  // Enough to tell two leads of the same customer apart.
  const sameCustomer = build({ leads: [
    { id: 'a', display_id: 'JPT-10', sales_stage: 'Quoted',
      customer: { display_name: 'Same GmbH' }, title: 'First project' },
    { id: 'b', display_id: 'JPT-11', sales_stage: 'New',
      customer: { display_name: 'Same GmbH' }, title: 'Second project' },
  ] });
  await sameCustomer.context.createQuote();
  await new Promise(resolve => setImmediate(resolve));
  const html = sameCustomer.elements['action-picker-results'].innerHTML;
  assert.ok(html.includes('JPT-10') && html.includes('JPT-11')
    && html.includes('First project') && html.includes('Second project'),
    `two leads of the same customer cannot be told apart: ${html}`);

  // With a lead already open, the reader is not asked twice.
  const withCurrent = build({ leads: emptyQueue, currentInquiry: { id: 'lead-2' } });
  await withCurrent.context.logFollowUp();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepStrictEqual(withCurrent.seen.shown, [],
    'the picker asked which lead when one was already open');
  assert.deepStrictEqual(withCurrent.seen.opened, [['lead-2', 'followup']]);
  assert.deepStrictEqual(withCurrent.seen.forms, ['followup']);

  // Searching narrows without changing what may be searched.
  const searching = build({ leads: emptyQueue });
  await searching.context.createQuote();
  await new Promise(resolve => setImmediate(resolve));
  searching.elements['action-picker-search'].value = 'Zweite';
  await searching.context.BusinessActionPicker.search();
  const narrowed = searching.elements['action-picker-results'].innerHTML;
  assert.ok(narrowed.includes('JPT-2') && !narrowed.includes('JPT-1'), narrowed);

  // Cancelling closes the picker and starts nothing.
  const cancelled = build({ leads: emptyQueue });
  await cancelled.context.logIssue();
  await new Promise(resolve => setImmediate(resolve));
  cancelled.context.BusinessActionPicker.close();
  assert.deepStrictEqual(cancelled.seen.hidden, ['action-picker-modal']);
  assert.deepStrictEqual(cancelled.seen.opened, []);
  assert.deepStrictEqual(cancelled.seen.forms, []);

  // A lead that could not be opened starts nothing: the form belongs to the
  // panel, and there is no panel.
  const unopened = build({ leads: emptyQueue, opens: false });
  await unopened.context.logIssue();
  await new Promise(resolve => setImmediate(resolve));
  assert.strictEqual(await unopened.context.BusinessActionPicker.choose(0), false);
  assert.deepStrictEqual(unopened.seen.forms, [],
    'a form was opened for a lead whose panel never came up');

  // A technical account cannot start these; the action does nothing at all.
  const tech = build({ leads: emptyQueue, role: 'tech' });
  await tech.context.logIssue();
  await tech.context.newSampleRequest();
  assert.deepStrictEqual(tech.seen.shown, [],
    'a technical account was offered a creation it cannot perform');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def main() -> None:
    result = subprocess.run(
        ["node", "-e", HARNESS], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: every create button starts its record from an empty queue")


if __name__ == "__main__":
    main()
