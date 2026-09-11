"""A panel action owns its own editor, from the click to the last await.

An independent audit reproduced eight defects that the existing tests missed,
because those tests checked function contracts - was it called, with what -
rather than following one user operation through every wait in it. These are
the same eight scenarios written as the behaviour that has to hold, with the
real modules loaded and the responses held open by hand.

The pattern in all of them: identity was checked once, early, and every wait
after that let the reader move on while the tail carried on acting on whatever
panel had arrived meanwhile.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PRELUDE = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
};
const tick = () => new Promise(resolve => setImmediate(resolve));

// A DOM small enough to reason about: every element is a real object, so a
// form held by one action and a form belonging to another are distinguishable.
function build(extra = {}) {
  const elements = {};
  const make = id => {
    const node = {
      id, value: '', textContent: '', innerHTML: '', disabled: false,
      dataset: {}, attributes: {}, children: [],
      classList: {
        names: new Set(),
        contains(name) { return name !== 'hidden'; },
        add(name) { this.names.add(name); },
        remove(name) { this.names.delete(name); },
        toggle(name, on) { on ? this.names.add(name) : this.names.delete(name); },
      },
      setAttribute(name, value) { this.attributes[name] = value; },
      removeAttribute(name) { delete this.attributes[name]; },
      hasAttribute(name) { return name in this.attributes; },
      focus() {},
      matches: () => true,
      // Walks descendants, like the real one. Returning only direct children
      // was the blind spot an independent audit found: a save button nested
      // inside the form was never frozen in the test, so the test could not
      // see the order-of-operations defect that stopped the save from being
      // sent at all.
      querySelectorAll() {
        const found = [];
        const visit = node => node.children.forEach(child => {
          found.push(child);
          visit(child);
        });
        visit(this);
        return found;
      },
      scrollIntoView() {},
      files: null,
    };
    return node;
  };
  const el = id => (elements[id] ||= make(id));
  const seen = { generation: 1, notices: [], alerts: [], renders: 0, hides: 0,
                 counts: 0, navOnly: 0 };
  const context = {
    console: { log() {}, error() {} },
    State: { user: { id: 'owner' }, currentInquiry: { id: 'A' } },
    document: {
      getElementById: el,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
    },
    I18n: { t: (text, params = {}) => Object.entries(params)
      .reduce((acc, [key, value]) => acc.replaceAll(`{${key}}`, value), text) },
    escapeHtml: value => String(value ?? ''),
    notify: message => { seen.notices.push(String(message)); },
    alert: message => { seen.alerts.push(String(message)); },
    confirm: () => true,
    setText: (id, value) => { el(id).textContent = value; },
    renderPanelContent: () => { seen.renders += 1; },
    renderPanelTabs: () => {},
    refreshAllCounts: async () => { seen.counts += 1; return true; },
    refreshNavigationCounts: async () => { seen.navOnly += 1; return true; },
    hideFollowUpForm: () => { seen.hides += 1; },
    hideAttachmentForm: () => { seen.hides += 1; },
    hideSampleTaskForm: () => { seen.hides += 1; },
    // Missing this one made a successful after-sales save throw on its last
    // line and report itself as "saved but not refreshed": the page has the
    // function, so the double had to as well.
    hideAfterSalesForm: () => { seen.hides += 1; },
    RoleCapabilities: { isTech: () => false, canManageTaskRequests: () => true,
                        canCreateLeads: () => true },
    PanelDirtyState: { reset() {}, confirmDiscard: () => true },
    ...extra,
  };
  // The session is what identifies an edit: the customer, and which visit.
  context.InquiryPanelSession = {
    capture: () => Object.freeze({
      leadId: context.State.currentInquiry?.id, generation: seen.generation }),
    isCurrent: session => session.generation === seen.generation
      && session.leadId === context.State.currentInquiry?.id,
  };
  context.window = context;
  vm.createContext(context);
  context._el = el;
  context._seen = seen;
  return context;
}

// The panel's forms as the templates actually build them: the save button is
// inside the form, so freezing the form freezes the button too.
function form(context, formId, fieldIds) {
  const container = context._el(formId);
  container.children = fieldIds.map(id => context._el(id));
  return container;
}

function load(context, file) {
  vm.runInContext(
    fs.readFileSync(process.env.JPT_ROOT + '/frontend/js/' + file, 'utf8'),
    context, { filename: file });
}

function loadPanelAction(context) {
  load(context, 'modules/inquiry-edit-freeze.js');
  load(context, 'modules/inquiry-panel-action.js');
}
"""

A01_A02 = PRELUDE + r"""
// A01 · the tail of an older save must not close or unlock the form the reader
// has since opened. A02 · the fields it submitted are held while it is in
// flight, so nothing typed afterwards is silently thrown away.
async function tailDoesNotTouchTheNewPanel() {
  const counts = deferred();
  const context = build({
    ApiClient: { addFollowUp: async () => ({ id: 'saved' }) },
    refreshCurrentInquiryData: async () => true,
  });
  context.refreshAllCounts = () => counts.promise;
  loadPanelAction(context);
  load(context, 'modules/followups-actions.js');

  const form = context._el('followup-form');
  const content = context._el('fu-content');
  const button = context._el('fu-save-btn');
  form.children = [content, button];
  content.value = 'first';
  context._el('fu-index').value = '-1';

  const saving = context.saveFollowUp();
  await tick();
  assert.equal(content.disabled, true,
    'the field stayed editable while its own save was in flight');
  assert.equal(button.disabled, true);

  // The reader opens somebody else while the counts are still refreshing, and
  // starts a save of their own there.
  context._seen.generation += 1;
  context.State.currentInquiry = { id: 'B' };
  const otherForm = context._el('followup-form');
  otherForm.disabled = false;
  button.disabled = true;

  counts.resolve(true);
  await saving;

  assert.equal(context._seen.hides, 0,
    "the older save closed the form belonging to the customer now on screen");
  assert.equal(button.disabled, true,
    "the older save unlocked the new panel's save button");
  assert.equal(context._seen.notices.length, 0,
    'the older save reported itself over the new panel');
}

// The ordinary path still finishes: same customer throughout.
async function theOrdinaryPathStillCompletes() {
  const context = build({
    ApiClient: { addFollowUp: async () => ({ id: 'saved' }) },
    refreshCurrentInquiryData: async () => true,
  });
  loadPanelAction(context);
  load(context, 'modules/followups-actions.js');
  const form = context._el('followup-form');
  const content = context._el('fu-content');
  const button = context._el('fu-save-btn');
  form.children = [content, button];
  content.value = 'first';
  context._el('fu-index').value = '-1';

  await context.saveFollowUp();
  assert.equal(context._seen.hides, 1, 'the form was left open');
  assert.equal(context._seen.notices.length, 1, 'the save was not reported');
  assert.equal(content.disabled, false, 'the field was left frozen');
  assert.equal(button.disabled, false, 'the button was left locked');
}

// A02 · what was submitted is what the field said, and nothing typed during
// the request is lost without a word - because typing is impossible.
async function nothingTypedDuringTheRequestIsLost() {
  const write = deferred();
  let submitted = null;
  const context = build({
    ApiClient: { addFollowUp: async (id, data) => {
      submitted = data.content; return write.promise; } },
    refreshCurrentInquiryData: async () => true,
  });
  loadPanelAction(context);
  load(context, 'modules/followups-actions.js');
  const form = context._el('followup-form');
  const content = context._el('fu-content');
  form.children = [content, context._el('fu-save-btn')];
  content.value = 'first';
  context._el('fu-index').value = '-1';

  const saving = context.saveFollowUp();
  await tick();
  assert.equal(content.disabled, true,
    'the field could still be typed into, so a second version would vanish');
  write.resolve({});
  await saving;
  assert.equal(submitted, 'first');
  assert.equal(content.disabled, false, 'the field was not handed back');
}

(async () => {
  await tailDoesNotTouchTheNewPanel();
  await theOrdinaryPathStillCompletes();
  await nothingTypedDuringTheRequestIsLost();
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


A03 = PRELUDE + r"""
// A03 · written, then the panel could not be re-read. The issue exists; being
// told "error saving" is what makes somebody log it a second time.
async function writtenThenRefreshFailed(module, opener, fields, apiMethod) {
  let writes = 0;
  const context = build({
    ApiClient: new Proxy({}, { get: (_, name) => async () => {
      if (name === apiMethod) writes += 1;
      return { id: 'written' };
    } }),
    refreshCurrentInquiryData: async () => { throw new Error('read failed'); },
  });
  context.State.currentInquiry = { id: 'A', _lead: { id: 'A', row_version: 1 } };
  loadPanelAction(context);
  load(context, module);
  for (const [id, value] of Object.entries(fields)) context._el(id).value = value;
  await context[opener]();

  assert.equal(writes, 1, `${module}: the write did not happen once`);
  assert.deepEqual(context._seen.alerts, [],
    `${module}: a successful write was reported as an error: ${context._seen.alerts}`);
  assert.ok(context._seen.notices.some(text => /saved/i.test(text)
    && /refresh/i.test(text)),
    `${module}: nothing said it was written but not redrawn: ${context._seen.notices}`);
  assert.ok(!context._seen.notices.some(text => /error saving/i.test(text)),
    `${module}: the reader was told it failed, which invites a second one`);
}

// And a write that really failed, with the reader still there, is still an
// error they can act on.
async function writeReallyFailed(module, opener, fields) {
  const context = build({
    ApiClient: new Proxy({}, { get: () => async () => {
      throw new Error('the server refused it');
    } }),
    refreshCurrentInquiryData: async () => true,
  });
  context.State.currentInquiry = { id: 'A', _lead: { id: 'A', row_version: 1 } };
  loadPanelAction(context);
  load(context, module);
  for (const [id, value] of Object.entries(fields)) context._el(id).value = value;
  await context[opener]();
  assert.equal(context._seen.alerts.length, 1,
    `${module}: a real failure was not reported to the reader`);
}

(async () => {
  for (const [module, opener, fields, method] of [
    ['modules/aftersales-actions.js', 'saveAfterSales',
     { 'as-description': 'issue', 'as-index': '-1' }, 'createAfterSalesTask'],
    ['modules/followups-actions.js', 'saveFollowUp',
     { 'fu-content': 'note', 'fu-index': '-1' }, 'addFollowUp'],
    ['modules/lead-closure.js', 'closeCurrentLead',
     { 'lead-close-reason-code': 'price' }, 'updateLead'],
  ]) {
    await writtenThenRefreshFailed(module, opener, fields, method);
    await writeReallyFailed(module, opener, fields);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


A04 = PRELUDE + r"""
// A04 - the picker's action must run on the lead that was chosen, and on
// nothing else. "The request finished" is not "my lead is open".
function pickerContext(loads) {
  const context = build({
    ApiClient: { listAllLeads: async () => ({
      items: [{ id: 'A', company_name: 'Alpha', display_id: 'JPT-A' }],
      complete: true }) },
    PagedFetch: { note: () => '' },
    WorklistUI: { select() {} },
    InquiryPanelData: { load: id => loads(id) },
    showModal() {}, hideModal() {},
  });
  context.State.currentInquiry = null;
  load(context, 'modules/inquiry-panel.js');
  load(context, 'modules/business-action-picker.js');
  return context;
}

async function theActionRunsOnTheLeadThatWasChosen() {
  const ran = [];
  const context = pickerContext(async id => ({ id, company_name: id }));
  await context.BusinessActionPicker.open({ title: 'Log issue',
    context: 'aftersales', then: () => ran.push(context.State.currentInquiry?.id) });
  assert.equal(await context.BusinessActionPicker.choose(0), true);
  assert.deepEqual(ran, ['A'], 'the chosen lead never got its form');
}

async function theActionDoesNotRunOnWhoeverArrivedInstead() {
  const a = deferred(), b = deferred();
  const ran = [];
  const context = pickerContext(id => (id === 'A' ? a.promise : b.promise));
  await context.BusinessActionPicker.open({ title: 'Log issue',
    context: 'aftersales', then: () => ran.push(context.State.currentInquiry?.id) });

  const chosen = context.BusinessActionPicker.choose(0);
  // Before A has loaded, the reader opens B from the list behind the modal.
  const switched = context.openInquiryPanel('B', 'deal');
  b.resolve({ id: 'B', company_name: 'Beta' });
  assert.equal(await switched, true, 'the panel the reader asked for did not open');
  a.resolve({ id: 'A', company_name: 'Alpha' });

  assert.equal(await chosen, false,
    'a superseded choice reported itself as opened');
  assert.deepEqual(ran, [],
    `the form for A was opened on ${ran[0]} instead`);
  assert.equal(context.State.currentInquiry?.id, 'B',
    "the older choice took the screen back off the reader");
}

// The same panel, re-opened after a look at somebody else, is a new visit: an
// action begun on the first visit must not act on the second.
async function reopeningTheSameLeadIsANewVisit() {
  const first = deferred(), second = deferred();
  let call = 0;
  const context = pickerContext(id => (id === 'A'
    ? (call++ === 0 ? first.promise : second.promise)
    : Promise.resolve({ id, company_name: id })));
  await context.BusinessActionPicker.open({ title: 'Log issue',
    context: 'aftersales', then: () => {} });
  const chosen = context.BusinessActionPicker.choose(0);
  await context.openInquiryPanel('B', 'deal');
  const back = context.openInquiryPanel('A', 'deal');
  second.resolve({ id: 'A', company_name: 'Alpha' });
  await back;
  first.resolve({ id: 'A', company_name: 'Alpha' });
  assert.equal(await chosen, false,
    'the first visit\'s choice acted on the panel re-opened since');
}

(async () => {
  await theActionRunsOnTheLeadThatWasChosen();
  await theActionDoesNotRunOnWhoeverArrivedInstead();
  await reopeningTheSameLeadIsANewVisit();
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


A05 = PRELUDE + r"""
// A05 - the email typed into the manual entry form is what the enquiry is
// reached by. It was used to look the company up and then dropped.
function entryContext(form, extra = {}) {
  const calls = { customers: 0, contacts: [], leads: [] };
  const context = build({
    RoleCapabilities: { canCreateLeads: () => true },
    NewInquiryForm: {
      read: () => ({ ...form }), missingFields: () => [],
      freeze() {}, setStatus() {}, clear() {}, renderMatches: () => '',
    },
    ApiClient: {
      createCustomer: async () => {
        calls.customers += 1;
        return { id: 'cust-new', display_name: form.companyName };
      },
      createCustomerContact: async (customerId, data) => {
        calls.contacts.push({ customerId, ...data });
        return { id: `contact-${calls.contacts.length}`, ...data };
      },
      createLead: async data => {
        calls.leads.push(data);
        if (extra.leadFails && calls.leads.length === 1) {
          throw new Error('the server refused it');
        }
        return { id: 'lead-1', display_id: 'JPT-1' };
      },
    },
    openInquiryPanel: async () => true,
    hideModal() {},
  });
  load(context, 'modules/new-inquiry-state.js');
  load(context, 'modules/new-inquiry-actions.js');
  context._calls = calls;
  return context;
}

async function aNewCompanyKeepsTheAddressItWroteFrom() {
  const context = entryContext({ companyName: 'Alpha GmbH', title: 'Cutting head',
    contactEmail: 'Anna.Weber@alpha.de' });
  await context.NewInquiryActions.save();
  const { contacts, leads } = context._calls;
  assert.deepEqual(contacts, [{ customerId: 'cust-new',
    email: 'Anna.Weber@alpha.de', is_primary: true }],
    `the address was not written down: ${JSON.stringify(contacts)}`);
  assert.equal(leads[0].primary_contact_id, 'contact-1',
    'the enquiry does not point at the person who wrote in');
}

async function anEnquiryWithNoAddressCreatesNoContact() {
  const context = entryContext({ companyName: 'Alpha GmbH', title: 'Cutting head',
    contactEmail: '   ' });
  await context.NewInquiryActions.save();
  assert.deepEqual(context._calls.contacts, [],
    'a blank address was filed as a contact');
  assert.equal(context._calls.leads[0].primary_contact_id, undefined);
}

async function anAddressAlreadyOnFileIsNotFiledTwice() {
  const context = entryContext({ companyName: 'Alpha GmbH', title: 'Second job',
    contactEmail: 'ANNA.WEBER@alpha.de' });
  context.NewInquiryState.chooseCustomer({ id: 'cust-1', display_name: 'Alpha GmbH',
    contacts: [{ id: 'contact-old', email: 'anna.weber@alpha.de', is_primary: true }] });
  await context.NewInquiryActions.save();
  assert.deepEqual(context._calls.contacts, [],
    'the same address was filed a second time under a different spelling');
  assert.equal(context._calls.leads[0].primary_contact_id, 'contact-old',
    'the enquiry does not point at the contact already on file');
}

// Somebody else at a company already on file: they are added, but whoever the
// reader marked as that company's main contact stays their main contact.
async function aSecondPersonDoesNotTakeOverTheCompany() {
  const context = entryContext({ companyName: 'Alpha GmbH', title: 'Third job',
    contactEmail: 'bernd@alpha.de' });
  context.NewInquiryState.chooseCustomer({ id: 'cust-1', display_name: 'Alpha GmbH',
    contacts: [{ id: 'contact-old', email: 'anna.weber@alpha.de', is_primary: true }] });
  await context.NewInquiryActions.save();
  assert.deepEqual(context._calls.contacts, [{ customerId: 'cust-1',
    email: 'bernd@alpha.de', is_primary: false }],
    `${JSON.stringify(context._calls.contacts)}`);
  assert.equal(context._calls.leads[0].primary_contact_id, 'contact-1',
    'the enquiry does not point at the person who sent it');
}

// A failed save is retried by clicking again. That must not leave a second
// company or a second copy of the same person behind.
async function retryingAFailedSaveDuplicatesNothing() {
  const context = entryContext({ companyName: 'Alpha GmbH', title: 'Cutting head',
    contactEmail: 'anna@alpha.de' }, { leadFails: true });
  assert.equal(await context.NewInquiryActions.save(), null,
    'a refused save reported success');
  await context.NewInquiryActions.save();
  const { customers, contacts, leads } = context._calls;
  assert.equal(customers, 1, `${customers} companies were created`);
  assert.equal(contacts.length, 1, `${contacts.length} copies of the same person`);
  assert.equal(leads.length, 2);
  assert.equal(leads[1].primary_contact_id, 'contact-1',
    'the retry lost the contact the first attempt recorded');
}

(async () => {
  await aNewCompanyKeepsTheAddressItWroteFrom();
  await anEnquiryWithNoAddressCreatesNoContact();
  await anAddressAlreadyOnFileIsNotFiledTwice();
  await aSecondPersonDoesNotTakeOverTheCompany();
  await retryingAFailedSaveDuplicatesNothing();
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


A06 = PRELUDE + r"""
// A06 - a customer search answered out of order. The list on screen and the
// customer chosen from it belong to the same query, or to neither.
function matchContext(answers) {
  let typed = 'A';
  const context = build({
    NewInquiryForm: {
      read: () => ({ companyName: typed }), setStatus() {}, renderMatches: () => '',
      missingFields: () => [], freeze() {}, clear() {},
    },
    ApiClient: { matchCustomers: () => answers[typed] },
    RoleCapabilities: { canCreateLeads: () => true },
  });
  load(context, 'modules/new-inquiry-state.js');
  load(context, 'modules/new-inquiry-actions.js');
  context._type = value => { typed = value; };
  return context;
}

async function anOlderSearchDoesNotReplaceTheNewerList() {
  const first = deferred(), second = deferred();
  const context = matchContext({ A: first.promise, B: second.promise });
  const older = context.NewInquiryActions.findCustomers();
  context._type('B');
  const newer = context.NewInquiryActions.findCustomers();
  second.resolve([{ id: 'cust-b', display_name: 'Beta' }]);
  await newer;
  context.NewInquiryActions.pickCustomer(0);
  first.resolve([{ id: 'cust-a', display_name: 'Alpha' }]);
  await older;

  const state = context.NewInquiryState.get();
  assert.equal(state.matches[0].id, 'cust-b',
    'the list is answering a search the reader has moved on from');
  assert.equal(state.customer?.id, 'cust-b',
    'the customer the reader chose was cleared by an older answer');
}

async function anOlderSearchFailureDoesNotSpeakForTheNewerOne() {
  const first = deferred(), second = deferred();
  const statuses = [];
  const context = matchContext({ A: first.promise, B: second.promise });
  context.NewInquiryForm.setStatus = message => statuses.push(String(message));
  const older = context.NewInquiryActions.findCustomers();
  context._type('B');
  const newer = context.NewInquiryActions.findCustomers();
  second.resolve([{ id: 'cust-b', display_name: 'Beta' }]);
  await newer;
  first.reject(new Error('lost the network'));
  await older;
  assert.ok(!statuses.some(text => /lost the network/.test(text)),
    `an older search reported its failure over the newer one: ${statuses}`);
}

// The search still works when nothing races it.
async function anOrdinarySearchFillsTheList() {
  const context = matchContext({ A: Promise.resolve([
    { id: 'cust-a', display_name: 'Alpha' }]) });
  await context.NewInquiryActions.findCustomers();
  assert.equal(context.NewInquiryState.get().matches[0].id, 'cust-a');
}

// A07 in the same shape: refreshing the counts after a manual save must not
// take the screen off whatever the reader opened while it ran.
async function theNewEnquiryDoesNotStealTheReadersChoice() {
  const counts = deferred();
  const opened = [];
  const context = build({
    RoleCapabilities: { canCreateLeads: () => true },
    NewInquiryForm: { read: () => ({ companyName: 'Alpha', title: 'need' }),
      missingFields: () => [], freeze() {}, setStatus() {}, clear() {} },
    ApiClient: {
      createCustomer: async () => ({ id: 'cust-new', display_name: 'Alpha' }),
      createLead: async () => ({ id: 'lead-new', display_id: 'JPT-1' }),
    },
    openInquiryPanel: async id => { opened.push(id); return true; },
    hideModal() {},
  });
  context.refreshAllCounts = () => counts.promise;
  load(context, 'modules/new-inquiry-state.js');
  load(context, 'modules/new-inquiry-actions.js');

  const saving = context.NewInquiryActions.save();
  await tick();
  context.State.currentInquiry = { id: 'B' };   // the reader opens something
  opened.push('B');
  counts.resolve(true);
  await saving;
  assert.deepEqual(opened, ['B'],
    'the new enquiry opened itself over the panel the reader had chosen');
}

async function theNewEnquiryOpensWhenNobodyMovedOn() {
  const opened = [];
  const context = build({
    RoleCapabilities: { canCreateLeads: () => true },
    NewInquiryForm: { read: () => ({ companyName: 'Alpha', title: 'need' }),
      missingFields: () => [], freeze() {}, setStatus() {}, clear() {} },
    ApiClient: {
      createCustomer: async () => ({ id: 'cust-new', display_name: 'Alpha' }),
      createLead: async () => ({ id: 'lead-new', display_id: 'JPT-1' }),
    },
    openInquiryPanel: async id => { opened.push(id); return true; },
    hideModal() {},
  });
  context.State.currentInquiry = null;
  load(context, 'modules/new-inquiry-state.js');
  load(context, 'modules/new-inquiry-actions.js');
  await context.NewInquiryActions.save();
  assert.deepEqual(opened, ['lead-new'],
    'the enquiry that was just recorded did not open');
}

(async () => {
  await anOlderSearchDoesNotReplaceTheNewerList();
  await anOlderSearchFailureDoesNotSpeakForTheNewerOne();
  await anOrdinarySearchFillsTheList();
  await theNewEnquiryDoesNotStealTheReadersChoice();
  await theNewEnquiryOpensWhenNobodyMovedOn();
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


A07 = PRELUDE + r"""
// A07 - which query the cards on screen answer. Reading every page fixed rows
// going missing; it said nothing about the filter they belong to.
function worklistContext(answers) {
  let owner = 'A';
  const renders = [];
  const context = build({
    ApiClient: { listAllLeads: () => answers[owner] },
    getSharedLeadFilters: () => ({ owner }),
    WorklistSort: { handler: rows => rows },
    leadToCardItem: lead => lead,
    PagedFetch: { note: () => '' },
    // The queue draws through its workbench now. The double records what
    // reached the screen, the same way the old renderCards double did.
    HandlerWorkbench: {
      render: (rows, emptyCopy) => renders.push(rows.length
        ? rows.map(row => row.id) : `error:${emptyCopy?.text || emptyCopy?.title}`),
    },
    renderCards: (id, rows) => renders.push(rows.map(row => row.id)),
    setPanelError: (id, message) => renders.push(`error:${message}`),
  });
  load(context, 'modules/worklist-request.js');
  load(context, 'modules/handler-worklist.js');
  context._renders = renders;
  context._own = value => { owner = value; };
  return context;
}

async function theOlderAnswerDoesNotDrawOverTheNewerOne() {
  const first = deferred(), second = deferred();
  const context = worklistContext({ A: first.promise, B: second.promise });
  const older = context.loadHandler();
  context._own('B');
  const newer = context.loadHandler();
  second.resolve({ items: [{ id: 'lead-b' }], complete: true });
  await newer;
  first.resolve({ items: [{ id: 'lead-a' }], complete: true });
  await older;
  assert.deepEqual(context._renders, [['lead-b']],
    'the cards on screen answer a filter the reader has changed');
  assert.equal(context._el('inquiry-count').textContent, '1 leads');
}

async function anOlderFailureDoesNotEmptyTheNewerList() {
  const first = deferred(), second = deferred();
  const context = worklistContext({ A: first.promise, B: second.promise });
  const older = context.loadHandler();
  context._own('B');
  const newer = context.loadHandler();
  second.resolve({ items: [{ id: 'lead-b' }], complete: true });
  await newer;
  first.reject(new Error('lost the network'));
  await older;
  assert.deepEqual(context._renders, [['lead-b']],
    'an older query\'s failure replaced a list that had loaded');
  assert.equal(context._el('inquiry-count').textContent, '1 leads',
    'the count was overwritten by an older failure');
}

// A load with nothing racing it still draws, and a genuine failure is still
// reported.
// "All stages" is the empty value on that select, and `||` read it as nothing
// chosen: the option existed but the list stayed filtered to New.
async function allStagesReallyMeansAllStages() {
  const asked = [];
  const context = worklistContext({ A: Promise.resolve({ items: [], complete: true }) });
  context.ApiClient.listAllLeads = params => {
    asked.push(params.sales_stage);
    return Promise.resolve({ items: [], complete: true });
  };
  context._el('filter-stage').value = 'New';
  await context.loadHandler();
  context._el('filter-stage').value = '';
  await context.loadHandler();
  assert.deepEqual(asked, ['New', undefined],
    `the empty "all stages" value was replaced by a stage filter: ${asked}`);
}

async function anOrdinaryLoadDrawsAndAFailureIsReported() {
  const context = worklistContext({
    A: Promise.resolve({ items: [{ id: 'lead-a' }], complete: true }) });
  await context.loadHandler();
  assert.deepEqual(context._renders, [['lead-a']]);

  const failing = worklistContext({ A: Promise.reject(new Error('down')) });
  await failing.loadHandler();
  assert.ok(failing._renders.some(entry => String(entry).startsWith('error:')),
    'a failed load left the reader with no explanation');
}

(async () => {
  await theOlderAnswerDoesNotDrawOverTheNewerOne();
  await anOlderFailureDoesNotEmptyTheNewerList();
  await anOrdinaryLoadDrawsAndAFailureIsReported();
  await allStagesReallyMeansAllStages();
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


S01_S02 = PRELUDE + r"""
// S01 · a save that never happens. The freeze disables every control inside
// the form, the save button among them; asking "is a save already in flight?"
// after that always answered yes, so the function returned before sending
// anything - and before the finally that would have handed the fields back.
// The form was left dead: no request, no error, nothing typeable.
//
// S02 · a sampling save must give back its own button, not whichever button
// is on screen when it finishes.

const AFTERSALES = ['as-index', 'as-date', 'as-type', 'as-status', 'as-description',
                    'as-solution', 'as-satisfaction', 'as-lessons', 'as-remarks',
                    'as-save-btn'];
const FILES = ['attachment-index', 'attachment-file', 'attachment-category',
               'attachment-name', 'attachment-version', 'attachment-save-btn'];
const SAMPLE = ['sample-task-index', 'sample-task-create-token', 'sample-task-params',
                'sample-task-save'];

function afterSalesContext({ description = 'the head overheats' } = {}) {
  const calls = [];
  const context = build({
    ApiClient: {
      createAfterSalesTask: async (...args) => { calls.push(['create', ...args]); return { id: 'task' }; },
      updateAfterSalesTask: async (...args) => { calls.push(['update', ...args]); return { id: 'task' }; },
    },
    refreshCurrentInquiryData: async () => true,
  });
  loadPanelAction(context);
  load(context, 'modules/aftersales-actions.js');
  form(context, 'aftersales-form', AFTERSALES);
  context._el('as-description').value = description;
  context._el('as-index').value = '-1';
  context._calls = calls;
  return context;
}

async function anAfterSalesIssueIsActuallySent() {
  const context = afterSalesContext();
  await context.saveAfterSales();
  assert.equal(context._calls.length, 1,
    `the save sent ${context._calls.length} requests`);
  assert.deepEqual(context._seen.alerts, [], String(context._seen.alerts));
  assert.equal(context._seen.notices.length, 1, 'nothing said it was saved');
  assert.equal(context._el('as-description').disabled, false,
    'the form was left frozen after the save finished');
  assert.equal(context._el('as-save-btn').disabled, false,
    'the save button was left locked');
}

async function anEmptyAfterSalesFormCanStillBeFilledIn() {
  const context = afterSalesContext({ description: '' });
  await context.saveAfterSales();
  assert.equal(context._calls.length, 0, 'an empty issue was sent anyway');
  assert.equal(context._seen.alerts.length, 1, 'nothing said what was missing');
  assert.equal(context._el('as-description').disabled, false,
    'the reader was told to add a description into a field they cannot type in');
  assert.equal(context._el('as-save-btn').disabled, false,
    'the save button stayed locked, so they cannot try again');
}

async function aSecondClickWhileTheFirstIsInFlightSendsNothing() {
  const write = deferred();
  const calls = [];
  const context = build({
    ApiClient: { createAfterSalesTask: async () => { calls.push('create'); return write.promise; } },
    refreshCurrentInquiryData: async () => true,
  });
  loadPanelAction(context);
  load(context, 'modules/aftersales-actions.js');
  form(context, 'aftersales-form', AFTERSALES);
  context._el('as-description').value = 'the head overheats';
  context._el('as-index').value = '-1';

  const first = context.saveAfterSales();
  await tick();
  await context.saveAfterSales();          // the impatient second click
  write.resolve({ id: 'task' });
  await first;
  assert.equal(calls.length, 1, `${calls.length} issues were created`);
}

function filesContext({ withFile = true } = {}) {
  const calls = [];
  const context = build({
    ApiClient: {
      uploadAttachment: async (...args) => { calls.push(['upload', ...args]); return { id: 'a' }; },
      updateAttachment: async (...args) => { calls.push(['update', ...args]); return { id: 'a' }; },
    },
    refreshCurrentInquiryData: async () => true,
  });
  loadPanelAction(context);
  load(context, 'modules/files-actions.js');
  form(context, 'attachment-form', FILES);
  context._el('attachment-index').value = '-1';
  context._el('attachment-version').value = '1';
  context._el('attachment-category').value = 'quotation';
  if (withFile) context._el('attachment-file').files = [{ name: 'quote.pdf' }];
  context._calls = calls;
  return context;
}

async function aChosenFileIsActuallyUploaded() {
  const context = filesContext();
  await context.saveAttachment();
  assert.equal(context._calls.length, 1,
    `the upload sent ${context._calls.length} requests`);
  assert.deepEqual(context._seen.alerts, [], String(context._seen.alerts));
  assert.equal(context._el('attachment-category').disabled, false,
    'the form was left frozen after the upload finished');
}

async function anUploadWithNoFileLeavesTheFormUsable() {
  const context = filesContext({ withFile: false });
  await context.saveAttachment();
  assert.equal(context._calls.length, 0, 'an upload with no file was sent');
  assert.equal(context._seen.alerts.length, 1, 'nothing said a file was needed');
  assert.equal(context._el('attachment-file').disabled, false,
    'the reader was told to choose a file through a disabled field');
}

// S02 · the sampling save and the button it locked.
function samplingContext() {
  const calls = [];
  const context = build({
    ApiClient: {
      createPreSalesTask: async (...args) => { calls.push(['create', ...args]); return { id: 't' }; },
      updatePreSalesTask: async (...args) => { calls.push(['update', ...args]); return { id: 't' }; },
    },
    refreshCurrentInquiryData: async () => true,
    loadSampling: async () => true,
    SamplingFormController: { currentTask: () => null },
    SamplingFormData: {
      requestDescription: () => 'two heads for a trial',
      collect: () => ({ request_description: 'two heads for a trial' }),
      creationToken: () => 'token-1',
    },
  });
  loadPanelAction(context);
  load(context, 'modules/sampling-actions.js');
  form(context, 'sample-task-form', SAMPLE);
  context._el('sample-task-index').value = '-1';
  context._calls = calls;
  return context;
}

async function aSamplingSaveFreezesItsOwnFieldsAndSends() {
  const write = deferred();
  const context = samplingContext();
  context.ApiClient.createPreSalesTask = async () => { context._calls.push('create'); return write.promise; };
  const saving = context.saveSampleTask();
  await tick();
  assert.equal(context._el('sample-task-params').disabled, true,
    'the request went out with the fields still editable, so anything typed '
    + 'next would be neither sent nor kept');
  write.resolve({ id: 't' });
  await saving;
  assert.equal(context._calls.length, 1);
  assert.equal(context._el('sample-task-params').disabled, false,
    'the fields were left frozen');
  assert.equal(context._el('sample-task-save').disabled, false,
    'the save button was left locked');
}

async function anOlderSamplingSaveDoesNotUnlockTheNewPanel() {
  const write = deferred();
  const context = samplingContext();
  context.ApiClient.createPreSalesTask = async () => write.promise;
  const saving = context.saveSampleTask();
  await tick();

  // The reader opens somebody else and starts a save of their own there.
  context._seen.generation += 1;
  context.State.currentInquiry = { id: 'B' };
  const button = context._el('sample-task-save');
  button.disabled = true;

  write.resolve({ id: 't' });
  await saving;
  assert.equal(button.disabled, true,
    "the older sampling save unlocked the new panel's save button");
  assert.equal(context._seen.notices.length, 0,
    'the older sampling save reported itself over the new panel');
}

async function aSamplingSaveThatCouldNotRedrawLeavesTheNewFormOpen() {
  const context = samplingContext();
  context.refreshCurrentInquiryData = async () => { throw new Error('read failed'); };
  const hidden = [];
  context.hideSampleTaskForm = () => hidden.push('sample');
  // The reader has moved on by the time the write comes back.
  context.ApiClient.createPreSalesTask = async () => {
    context._seen.generation += 1;
    context.State.currentInquiry = { id: 'B' };
    return { id: 't' };
  };
  await context.saveSampleTask();
  assert.deepEqual(hidden, [],
    'the older sampling save closed the form belonging to the customer now on screen');
  assert.ok(context._seen.notices.some(text => /saved/i.test(text) && /refresh/i.test(text)),
    `nothing said it was written but not redrawn: ${context._seen.notices}`);
}

// The same rule as follow-ups, checked on each of these forms rather than
// assumed from one of them: an older save gives back the button it locked, and
// only if the panel is still the one it started on. The button is disabled
// before the freeze so it is not in the freeze's list - otherwise the freeze
// would hand it back unconditionally when the older save finished.
async function anOlderSaveDoesNotUnlockTheNewPanel(module, opener, formId,
                                                   fieldIds, buttonId, fields) {
  const write = deferred();
  const context = build({
    ApiClient: new Proxy({}, { get: () => async () => write.promise }),
  });
  // The real one answers false when the panel it belongs to is no longer the
  // one on screen. A double that always says true hands the tail a licence the
  // page would not give it - and hides whichever guard the module relies on.
  context.refreshCurrentInquiryData = async (leadId, action) =>
    !action || context.InquiryPanelAction.isCurrent(action);
  loadPanelAction(context);
  load(context, module);
  form(context, formId, fieldIds);
  for (const [id, value] of Object.entries(fields)) context._el(id).value = value;
  if (fields['attachment-file'] === undefined && formId === 'attachment-form') {
    context._el('attachment-file').files = [{ name: 'quote.pdf' }];
  }

  const saving = context[opener]();
  await tick();
  context._seen.generation += 1;
  context.State.currentInquiry = { id: 'B' };
  const button = context._el(buttonId);
  button.disabled = true;                    // B has a save of its own in flight

  write.resolve({ id: 'written' });
  await saving;
  assert.equal(button.disabled, true,
    `${module}: an older save unlocked the new panel's save button`);
  assert.equal(context._seen.notices.length, 0,
    `${module}: an older save reported itself over the new panel: ${context._seen.notices}`);
}

(async () => {
  await anAfterSalesIssueIsActuallySent();
  await anEmptyAfterSalesFormCanStillBeFilledIn();
  await aSecondClickWhileTheFirstIsInFlightSendsNothing();
  await aChosenFileIsActuallyUploaded();
  await anUploadWithNoFileLeavesTheFormUsable();
  await aSamplingSaveFreezesItsOwnFieldsAndSends();
  await anOlderSamplingSaveDoesNotUnlockTheNewPanel();
  await aSamplingSaveThatCouldNotRedrawLeavesTheNewFormOpen();
  await anOlderSaveDoesNotUnlockTheNewPanel(
    'modules/aftersales-actions.js', 'saveAfterSales', 'aftersales-form',
    AFTERSALES, 'as-save-btn',
    { 'as-description': 'the head overheats', 'as-index': '-1' });
  await anOlderSaveDoesNotUnlockTheNewPanel(
    'modules/files-actions.js', 'saveAttachment', 'attachment-form',
    FILES, 'attachment-save-btn',
    { 'attachment-index': '-1', 'attachment-version': '1' });
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


S03 = PRELUDE + r"""
// S03 · refreshAllCounts answers false when it could not re-read the numbers,
// and keeps the reason to itself. Ignoring that answer told the reader the
// screen was up to date while the counts beside the modules were the old ones.
// And an archive that landed, followed by a failed re-read, was reported as a
// failed archive - which is how the same record gets archived twice.

async function aStaleCountIsSaidOutLoud(module, opener, fields, formId, fieldIds) {
  const context = build({
    ApiClient: new Proxy({}, { get: () => async () => ({ id: 'written' }) }),
    refreshCurrentInquiryData: async () => true,
  });
  context.refreshAllCounts = async () => false;   // the numbers stayed old
  loadPanelAction(context);
  load(context, module);
  form(context, formId, fieldIds);
  for (const [id, value] of Object.entries(fields)) context._el(id).value = value;
  await context[opener]();

  assert.deepEqual(context._seen.alerts, [], `${module}: ${context._seen.alerts}`);
  assert.equal(context._seen.notices.length, 1,
    `${module}: ${context._seen.notices.length} notices`);
  assert.ok(/counts/i.test(context._seen.notices[0]),
    `${module}: a stale count was reported as an ordinary success: `
    + context._seen.notices[0]);
}

async function anArchiveThatLandedIsNotCalledAFailure(module, opener, apiName) {
  let archives = 0;
  const context = build({
    ApiClient: new Proxy({}, { get: (_, name) => async () => {
      if (name === apiName) archives += 1;
      return { id: 'archived' };
    } }),
    refreshCurrentInquiryData: async () => { throw new Error('read failed'); },
  });
  context.State.currentInquiry = {
    id: 'A', _lead: { id: 'A', row_version: 1 },
    follow_ups: [{ id: 'f1', content: 'called them' }],
    after_sales: [{ id: 'i1', row_version: 1 }],
    attachments: [{ id: 'a1', original_name: 'quote.pdf' }],
  };
  loadPanelAction(context);
  load(context, module);
  await context[opener](0);

  assert.equal(archives, 1, `${module}: the archive did not happen once`);
  assert.deepEqual(context._seen.alerts, [],
    `${module}: an archive that landed was reported as an error: ${context._seen.alerts}`);
  assert.ok(context._seen.notices.some(text => /archived/i.test(text)
    && /refresh/i.test(text)),
    `${module}: nothing said it was archived but not redrawn: ${context._seen.notices}`);
}

(async () => {
  await aStaleCountIsSaidOutLoud(
    'modules/followups-actions.js', 'saveFollowUp',
    { 'fu-content': 'called them', 'fu-index': '-1' },
    'followup-form', ['fu-content', 'fu-index', 'fu-save-btn']);
  await aStaleCountIsSaidOutLoud(
    'modules/aftersales-actions.js', 'saveAfterSales',
    { 'as-description': 'the head overheats', 'as-index': '-1' },
    'aftersales-form', ['as-description', 'as-index', 'as-save-btn']);

  await anArchiveThatLandedIsNotCalledAFailure(
    'modules/followups-actions.js', 'archiveFollowUp', 'archiveActivity');
  await anArchiveThatLandedIsNotCalledAFailure(
    'modules/aftersales-actions.js', 'archiveAfterSales', 'archiveAfterSalesTask');
  await anArchiveThatLandedIsNotCalledAFailure(
    'modules/files-actions.js', 'archiveAttachment', 'archiveAttachment');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def run(script: str, label: str) -> None:
    import os

    env = dict(os.environ, JPT_ROOT=str(ROOT))
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True,
        check=False, env=env,
    )
    assert result.returncode == 0, f"{label}: {result.stderr or result.stdout}"


def main() -> None:
    run(A01_A02, "A01/A02 panel action lifecycle")
    run(A03, "A03 written versus redrawn")
    run(A04, "A04 the picker's action runs on the lead it chose")
    run(A05, "A05 the address the enquiry arrived from is kept")
    run(A06, "A06 search answers and the customer chosen from them")
    run(A07, "A07 which query the cards on screen answer")
    run(S01_S02, "S01/S02 a save that is actually sent, and its own button")
    run(S03, "S03 done, but the screen could not be brought up to date")
    print("PASS: a panel action owns its editor from the click to the last await")


if __name__ == "__main__":
    main()
