"""Contracts for one-shot aggregate saves and stale panel response isolation."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
API = (ROOT / "frontend/js/api-client.js").read_text(encoding="utf-8")
SAVE = (ROOT / "frontend/js/modules/inquiry-save.js").read_text(encoding="utf-8")
PANEL = (ROOT / "frontend/js/modules/inquiry-panel.js").read_text(encoding="utf-8")


assert "saveInquiryAggregate" in API
assert "`/leads/${id}/aggregate`" in API
assert "await ApiClient.saveInquiryAggregate" in SAVE
assert "existingContact?.updated_at" in SAVE
assert "await ApiClient.updateCustomer(" not in SAVE
assert "await ApiClient.updateCustomerContact(" not in SAVE
assert "await ApiClient.createCustomerContact(" not in SAVE
assert "await ApiClient.updateLead(" not in SAVE
assert "inquirySaveEpoch" in SAVE
assert "requestIsCurrent()" in SAVE
assert "InquiryPanelSession" in PANEL
assert "generation: inquiryPanelRequestId" in PANEL


def _run_save_race_contract() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const deferred = () => {
  let resolve;
  const promise = new Promise(res => { resolve = res; });
  return { promise, resolve };
};
const pending = { A: deferred(), B: deferred() };
const titleInput = { name: 'title', value: 'edited', type: 'text' };
const saveButton = { disabled: false, dataset: {} };
const content = {
  querySelectorAll: () => [titleInput],
  querySelector: () => null,
};
let generation = 1;
let renders = 0;
let refreshes = 0;
let notifications = 0;
const context = {
  console,
  State: { currentInquiry: null },
  document: {
    getElementById(id) {
      if (id === 'panel-save-btn') return saveButton;
      if (id === 'panel-content') return content;
      return null;
    },
    querySelector(selector) {
      if (selector === '.panel-tab.active') return { dataset: { tab: 'basic' } };
      return null;
    },
  },
  InquiryPanelSession: {
    capture() { return Object.freeze({ leadId: context.State.currentInquiry?.id, generation }); },
    isCurrent(session) {
      return session.generation === generation
        && session.leadId === context.State.currentInquiry?.id;
    },
  },
  ApiClient: { saveInquiryAggregate: id => pending[id].promise },
  getLeadPrimaryContact: () => null,
  validateContactFields: () => true,
  validateEmail: () => true,
  handleContactValidationError() {},
  renderPanelContent() { renders += 1; },
  refreshAllCounts: async () => { refreshes += 1; },
  notify() { notifications += 1; },
  alert() {},
  I18n: { t: text => text },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/inquiry-save.js', 'utf8'), context);

const inquiry = id => ({
  id, row_version: 1, stage: 'Following', product: 'Old',
  _lead: { id }, _customer: { id: `customer-${id}`, row_version: 2, contacts: [] },
});

(async () => {
  context.State.currentInquiry = inquiry('A');
  const saveA = context.saveInquiry();
  assert.strictEqual(saveButton.disabled, true);

  generation = 2;
  context.State.currentInquiry = inquiry('B');
  saveButton.disabled = false;
  delete saveButton.dataset.inquirySaveEpoch;
  const saveB = context.saveInquiry();
  assert.strictEqual(saveButton.disabled, true);

  pending.A.resolve({
    id: 'A', sales_stage: 'Won', product_category: 'A product', row_version: 2,
    customer: { id: 'customer-A' },
  });
  await saveA;
  assert.strictEqual(context.State.currentInquiry.id, 'B');
  assert.strictEqual(context.State.currentInquiry.stage, 'Following');
  assert.strictEqual(saveButton.disabled, true, 'stale A finally must not unlock B save');
  assert.strictEqual(renders, 0);
  assert.strictEqual(refreshes, 0);
  assert.strictEqual(notifications, 0);

  pending.B.resolve({
    id: 'B', sales_stage: 'Quoted', product_category: 'B product', row_version: 3,
    customer: { id: 'customer-B' },
  });
  await saveB;
  assert.strictEqual(context.State.currentInquiry.id, 'B');
  assert.strictEqual(context.State.currentInquiry.stage, 'Quoted');
  assert.strictEqual(saveButton.disabled, false);
  assert.strictEqual(renders, 1);
  assert.strictEqual(refreshes, 1);
  assert.strictEqual(notifications, 1);
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


def _run_edit_freeze_contract() -> None:
    """Typing during a save must not be quietly thrown away.

    The values are taken when the button is pressed. While the request was out
    the fields stayed editable, so a second version could be typed, never sent,
    and then wiped by the redraw that followed the first version's success.
    """
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

let resolveSave;
const saved = new Promise(res => { resolveSave = res; });
const field = { name: 'requirements', value: 'first version', type: 'text',
                disabled: false, attributes: {},
                setAttribute(key) { this.attributes[key] = ''; },
                removeAttribute(key) { delete this.attributes[key]; },
                hasAttribute(key) { return key in this.attributes; } };
const saveButton = { disabled: false, dataset: {} };
const content = {
  querySelectorAll: () => [field],
  querySelector: () => null,
};
let sent = null;
let renders = 0;
const context = {
  console,
  State: { currentInquiry: null },
  document: {
    getElementById(id) {
      if (id === 'panel-save-btn') return saveButton;
      if (id === 'panel-content') return content;
      return null;
    },
    querySelector(selector) {
      return selector === '.panel-tab.active' ? { dataset: { tab: 'basic' } } : null;
    },
  },
  InquiryPanelSession: {
    capture() { return Object.freeze({ leadId: context.State.currentInquiry?.id, generation: 1 }); },
    isCurrent(session) { return session.leadId === context.State.currentInquiry?.id; },
  },
  ApiClient: { saveInquiryAggregate: (id, body) => { sent = body; return saved; } },
  getLeadPrimaryContact: () => null,
  validateContactFields: () => true,
  validateEmail: () => true,
  handleContactValidationError() {},
  renderPanelContent() { renders += 1; },
  refreshAllCounts: async () => {},
  notify() {},
  alert() {},
  I18n: { t: text => text },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/inquiry-edit-freeze.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/inquiry-save.js', 'utf8'), context);

(async () => {
  context.State.currentInquiry = {
    id: 'A', row_version: 1, _lead: { id: 'A' },
    _customer: { id: 'customer-A', row_version: 2, contacts: [] },
  };
  const saving = context.saveInquiry();
  assert.strictEqual(field.disabled, true,
    'the field stayed editable while its own save was in flight, so a second '
    + 'version could be typed and then silently overwritten');
  assert.strictEqual(sent.lead.requirements, 'first version',
    'the request must carry what the field said when the button was pressed');

  resolveSave({ id: 'A', sales_stage: 'Following', product_category: null,
                row_version: 2, customer: { id: 'customer-A' } });
  await saving;
  assert.strictEqual(field.disabled, false,
    'the field was left frozen after the save finished');
  assert.strictEqual(renders, 1, 'the tab was not redrawn from the saved lead');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _run_edit_freeze_release_on_failure() -> None:
    """A failed save has to hand the fields back, or the retry is impossible."""
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

let rejectSave;
const saved = new Promise((_, rej) => { rejectSave = rej; });
const field = { name: 'requirements', value: 'first version', type: 'text',
                disabled: false, attributes: {},
                setAttribute(key) { this.attributes[key] = ''; },
                removeAttribute(key) { delete this.attributes[key]; },
                hasAttribute(key) { return key in this.attributes; } };
const saveButton = { disabled: false, dataset: {} };
const content = { querySelectorAll: () => [field], querySelector: () => null };
let alerts = 0;
const context = {
  console,
  State: { currentInquiry: null },
  document: {
    getElementById(id) {
      if (id === 'panel-save-btn') return saveButton;
      if (id === 'panel-content') return content;
      return null;
    },
    querySelector: () => null,
  },
  InquiryPanelSession: {
    capture() { return Object.freeze({ leadId: 'A', generation: 1 }); },
    isCurrent() { return true; },
  },
  ApiClient: { saveInquiryAggregate: () => saved },
  getLeadPrimaryContact: () => null,
  validateContactFields: () => true,
  validateEmail: () => true,
  handleContactValidationError() {},
  renderPanelContent() {},
  refreshAllCounts: async () => {},
  notify() {},
  alert() { alerts += 1; },
  I18n: { t: text => text },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/inquiry-edit-freeze.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/inquiry-save.js', 'utf8'), context);

(async () => {
  context.State.currentInquiry = {
    id: 'A', row_version: 1, _lead: { id: 'A' },
    _customer: { id: 'customer-A', row_version: 2, contacts: [] },
  };
  const saving = context.saveInquiry();
  assert.strictEqual(field.disabled, true);
  rejectSave(new Error('network is down'));
  await saving;
  assert.strictEqual(field.disabled, false,
    'a failed save left the form frozen, so the reader cannot try again');
  assert.strictEqual(saveButton.disabled, false, 'the save button stayed locked');
  assert.strictEqual(alerts, 1, 'the failure was not reported');
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


_run_save_race_contract()
_run_edit_freeze_contract()
_run_edit_freeze_release_on_failure()
print("PASS: inquiry panel submits one aggregate request and ignores stale saves")
