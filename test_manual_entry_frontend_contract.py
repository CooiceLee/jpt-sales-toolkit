"""The manual entry form, driven for real: matching, saving, failing, cancelling.

The button used to open the email parser, which asks for a document the caller
does not have. These run the three modules behind the new form with the
requests held open, so the states a person actually meets - searching, saving,
a save that fails, a second click, cancelling - are exercised rather than read.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# The page has to offer the entry point, and only to accounts that may use it.
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
assert 'id="new-inquiry-modal"' in INDEX, "the manual entry form is not on the page"
assert 'onclick="showNewInquiryModal()"' in INDEX
assert "data-lead-creator" in INDEX, (
    "the entry point is not marked for the accounts that may create leads"
)
for field in (
    "new-inquiry-company", "new-inquiry-email", "new-inquiry-country",
    "new-inquiry-city", "new-inquiry-title", "new-inquiry-product",
    "new-inquiry-application", "new-inquiry-date", "new-inquiry-requirements",
):
    assert f'id="{field}"' in INDEX, f"missing field: {field}"
    assert f'for="{field}"' in INDEX, f"{field} has no label of its own"

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

function build({ role = 'leader', matches = [], failCreateLead = false } = {}) {
    const deferred = () => {
      let resolve, reject;
      const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
      return { promise, resolve, reject };
    };
    const fields = {};
    [
      'new-inquiry-company', 'new-inquiry-email', 'new-inquiry-country',
      'new-inquiry-city', 'new-inquiry-title', 'new-inquiry-product',
      'new-inquiry-application', 'new-inquiry-date', 'new-inquiry-requirements',
    ].forEach(id => { fields[id] = { value: '', disabled: false, focus() {} }; });
    const status = { textContent: '', className: '' };
    const matchBox = { innerHTML: '' };
    const saveButton = { disabled: false };
    const body = {
      querySelectorAll: () => [...Object.values(fields), saveButton],
    };
    const seen = { shown: [], hidden: [], notices: [], counts: 0, opened: [] };
    const calls = [];
    const pending = { lead: deferred() };
    const context = {
      console,
      I18n: { t: (text, params = {}) =>
        String(text).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? `{${key}}`) },
      escapeHtml: value => String(value ?? ''),
      State: { user: { id: 'user-1', role } },
      RoleCapabilities: { isTech: () => role === 'tech',
                          canCreateLeads: () => ['leader', 'sales'].includes(role) },
      document: {
        getElementById: id => (
          id === 'new-inquiry-status' ? status
          : id === 'new-inquiry-matches' ? matchBox
          : id === 'new-inquiry-body' ? body
          : id === 'new-inquiry-save' ? saveButton
          : fields[id] || null),
        querySelectorAll: () => [],
      },
      showModal: id => seen.shown.push(id),
      hideModal: id => seen.hidden.push(id),
      notify: message => seen.notices.push(String(message)),
      refreshAllCounts: async () => { seen.counts += 1; return true; },
      openInquiryPanel: async id => { seen.opened.push(id); },
      ApiClient: {
        matchCustomers: async (email, company) => {
          calls.push({ method: 'matchCustomers', email, company });
          return matches;
        },
        createCustomer: async data => {
          calls.push({ method: 'createCustomer', data });
          return { id: 'customer-new', display_name: data.display_name };
        },
        createLead: async data => {
          calls.push({ method: 'createLead', data });
          if (failCreateLead) return pending.lead.promise;
          return { id: 'lead-new', display_id: 'JPT-2609-0001', ...data };
        },
      },
    };
    context.window = context;
    vm.createContext(context);
    for (const file of ['new-inquiry-state.js', 'new-inquiry-form.js',
                        'new-inquiry-actions.js']) {
      vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
    }
    return { context, fields, status, matchBox, saveButton, seen, calls, pending };
}

(async () => {
  // Nothing on file: search finds nothing, saving creates the company and the
  // enquiry, and the reader lands on what they just made.
  const fresh = build();
  fresh.context.showNewInquiryModal();
  assert.deepStrictEqual(fresh.seen.shown, ['new-inquiry-modal']);
  fresh.fields['new-inquiry-company'].value = 'Erste Laser GmbH';
  fresh.fields['new-inquiry-country'].value = 'Germany';
  await fresh.context.NewInquiryActions.findCustomers();
  assert.ok(fresh.matchBox.innerHTML.includes('create one'),
    `nothing told the reader a customer would be created: ${fresh.matchBox.innerHTML}`);

  fresh.fields['new-inquiry-title'].value = 'Cutting head enquiry';
  const created = await fresh.context.NewInquiryActions.save();
  assert.ok(created, 'the save produced nothing');
  const methods = fresh.calls.map(call => call.method);
  assert.deepStrictEqual(methods, ['matchCustomers', 'createCustomer', 'createLead']);
  const leadCall = fresh.calls.find(call => call.method === 'createLead');
  assert.strictEqual(leadCall.data.customer_id, 'customer-new');
  assert.strictEqual(leadCall.data.owner_id, 'user-1',
    'the enquiry was not filed under the person recording it');
  assert.strictEqual(leadCall.data.title, 'Cutting head enquiry');
  // Nothing invented: no stage, no currency, no grade the form made up.
  assert.ok(!('sales_stage' in leadCall.data), 'the form invented a stage');
  assert.ok(!('currency' in leadCall.data), 'the form invented a currency');
  assert.ok(!('quality_grade' in leadCall.data), 'the form invented a grade');
  assert.deepStrictEqual(fresh.seen.hidden, ['new-inquiry-modal']);
  assert.deepStrictEqual(fresh.seen.opened, ['lead-new'],
    'the reader was not shown the enquiry they had just recorded');
  assert.strictEqual(fresh.seen.counts, 1, 'the lists were not refreshed');
  assert.ok(fresh.seen.notices.some(text => text.includes('JPT-2609-0001')),
    `the confirmation does not name the enquiry: ${fresh.seen.notices}`);

  // A company already on file: chosen, not copied.
  const existing = build({ matches: [
    { id: 'customer-1', display_name: 'Erste Laser GmbH', city: 'Berlin', country: 'Germany' },
    { id: 'customer-2', display_name: 'Erste Laser GmbH', city: 'Hamburg', country: 'Germany' },
  ] });
  existing.fields['new-inquiry-company'].value = 'Erste Laser GmbH';
  await existing.context.NewInquiryActions.findCustomers();
  assert.ok(existing.matchBox.innerHTML.includes('Berlin')
    && existing.matchBox.innerHTML.includes('Hamburg'),
    'two customers of the same name cannot be told apart in the list');
  existing.context.NewInquiryActions.pickCustomer(1);
  existing.fields['new-inquiry-title'].value = 'Second project';
  await existing.context.NewInquiryActions.save();
  assert.ok(!existing.calls.some(call => call.method === 'createCustomer'),
    'a company already on file was created a second time');
  assert.strictEqual(
    existing.calls.find(call => call.method === 'createLead').data.customer_id,
    'customer-2', 'the enquiry went to the wrong branch of the same company');

  // Required fields are named before anything is sent.
  const empty = build();
  const nothing = await empty.context.NewInquiryActions.save();
  assert.strictEqual(nothing, undefined);
  assert.strictEqual(empty.calls.length, 0, 'an incomplete form still called the server');
  assert.ok(empty.status.textContent.includes('Company name'), empty.status.textContent);
  assert.ok(empty.status.className.includes('error'));

  // Each required field is named on its own: a company with no subject is
  // still an enquiry nobody can act on.
  const noSubject = build();
  noSubject.fields['new-inquiry-company'].value = 'Named but silent GmbH';
  await noSubject.context.NewInquiryActions.save();
  assert.strictEqual(noSubject.calls.length, 0,
    'an enquiry with no subject was sent to the server');
  assert.ok(noSubject.status.textContent.includes('about'),
    `the missing subject was not named: ${noSubject.status.textContent}`);

  // A save in flight: the form is held, a second click adds nothing, and a
  // failure gives the typing back so it can be retried.
  const slow = build({ failCreateLead: true });
  slow.fields['new-inquiry-company'].value = 'Slow GmbH';
  slow.fields['new-inquiry-title'].value = 'Held open';
  const saving = slow.context.NewInquiryActions.save();
  assert.strictEqual(slow.fields['new-inquiry-title'].disabled, true,
    'the form stayed editable while its own save was in flight');
  // Not awaited: a second save that goes through would block on the same held
  // response, and waiting for it here would hide the extra request rather than
  // catch it.
  const second = slow.context.NewInquiryActions.save();
  await new Promise(resolve => setImmediate(resolve));
  assert.strictEqual(
    slow.calls.filter(call => call.method === 'createLead').length, 1,
    'a second click during the save created a second enquiry');
  slow.pending.lead.reject(new Error('network is down'));
  await saving;
  await second;
  assert.strictEqual(slow.fields['new-inquiry-title'].disabled, false,
    'a failed save left the form frozen, so it cannot be retried');
  assert.strictEqual(slow.fields['new-inquiry-title'].value, 'Held open',
    'a failed save threw away what had been typed');
  assert.ok(slow.status.textContent.toLowerCase().includes('network is down'),
    `the failure was not reported: ${slow.status.textContent}`);
  assert.deepStrictEqual(slow.seen.hidden, [],
    'a failed save closed the form');

  // Cancelling leaves nothing behind.
  const cancelled = build();
  cancelled.fields['new-inquiry-company'].value = 'Typed then abandoned';
  cancelled.context.closeNewInquiryModal();
  assert.deepStrictEqual(cancelled.seen.hidden, ['new-inquiry-modal']);
  assert.strictEqual(cancelled.calls.length, 0, 'cancelling wrote something');
  assert.strictEqual(cancelled.fields['new-inquiry-company'].value, '');

  // A technical account is told, not shown a form it cannot use.
  const tech = build({ role: 'tech' });
  tech.context.showNewInquiryModal();
  assert.deepStrictEqual(tech.seen.shown, [],
    'the manual entry form opened for an account that cannot create leads');
  assert.ok(tech.seen.notices.length === 1
    && tech.seen.notices[0].toLowerCase().includes('assign'),
    `a technical account got no explanation: ${tech.seen.notices}`);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def main() -> None:
    result = subprocess.run(
        ["node", "-e", HARNESS], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: an enquiry can be recorded by hand, and every state is honest")


if __name__ == "__main__":
    main()
