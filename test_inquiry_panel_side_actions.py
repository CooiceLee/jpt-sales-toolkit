"""A sub-action that finishes late must not redraw somebody else's panel.

The main save already refuses to apply a response the reader has moved past.
The actions inside the panel - a follow-up, an after-sales issue, a file, a
close - did not: each reloaded the lead it had been given and repainted the
panel unconditionally. Save a follow-up on A, decide to abandon the form, open
B, and A's answer arrives to put A's follow-up under B's name.

These run the real modules, with the response held open, rather than reading
them for the names of functions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Every panel action reloads the lead through this one function, so that is
# where the identity check belongs.
CHOKE_POINT = (ROOT / "frontend/js/modules/followups-form.js").read_text(
    encoding="utf-8"
)
assert "async function refreshCurrentInquiryData" in CHOKE_POINT

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};

// One scenario: an action on lead A, held open, while the reader opens B.
function scenario(name, { modules, fields, run, countsWhenCurrent = false }) {
  const loads = { A: deferred(), B: deferred() };
  const calls = [];
  const seen = { renders: 0, tabs: 0, counts: 0, navOnly: 0, notes: 0, hides: 0,
                 alerts: [], sampling: 0, generation: 1, notices: [] };
  const elements = new Map(Object.entries(fields || {}));
  // The form the action hides when it finishes. Counting the class it adds is
  // how we see whether a late action closed a form the reader had opened.
  elements.set('followup-form', {
    classList: { add: () => { seen.hides += 1; }, remove: () => {} },
  });
  const context = {
    console,
    State: { currentInquiry: null, user: { id: 'user-1' }, inquiries: [] },
    document: {
      getElementById: id => elements.get(id) || null,
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    ApiClient: new Proxy({}, { get: (_, method) => (...args) => {
      calls.push({ method: String(method), args });
      return Promise.resolve({ id: 'issue-1', row_version: 1 });
    } }),
    InquiryPanelData: { load: id => loads[id].promise },
    // The panel session: which customer, and which visit to them.
    InquiryPanelSession: {
      capture: () => Object.freeze({
        leadId: context.State.currentInquiry?.id, generation: seen.generation }),
      isCurrent: session => session.generation === seen.generation
        && session.leadId === context.State.currentInquiry?.id,
    },
    RoleCapabilities: { isTech: () => false, canManageTaskRequests: () => true },
    SamplingFormController: { currentTask: () => null },
    SamplingFormData: {
      requestDescription: () => 'described', collect: () => ({ note: 'x' }),
      creationToken: () => 'token-1',
    },
    loadSampling: async () => { seen.sampling += 1; },
    renderPanelContent: () => { seen.renders += 1; },
    renderPanelTabs: () => { seen.tabs += 1; },
    refreshAllCounts: async () => { seen.counts += 1; },
    refreshNavigationCounts: async () => { seen.navOnly += 1; },
    notify: message => { seen.notes += 1; seen.notices.push(String(message)); },
    hideAttachmentForm: () => { seen.hides += 1; },
    PanelDirtyState: { reset: () => {} },
    hideSampleTaskForm: () => { seen.hides += 1; },
    switchModule: () => {},
    confirm: () => true,
    alert: message => { seen.alerts.push(String(message)); },
    escapeHtml: value => String(value ?? ''),
    I18n: { t: text => text },
  };
  context.window = context;
  vm.createContext(context);
  vm.runInContext(
    fs.readFileSync('frontend/js/modules/inquiry-panel-action.js', 'utf8'), context);
  for (const file of modules) {
    vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
  }
  return { name, context, loads, calls, seen, run, countsWhenCurrent };
}

const lead = id => ({
  id,
  row_version: 1,
  stage: 'Following',
  follow_ups: [{ id: 'fu-1', content: `${id} follow-up` }],
  after_sales: [{ id: 'as-1', title: `${id} issue` }],
  attachments: [{ id: 'att-1', original_name: `${id}.pdf` }],
});

const scenarios = [
  scenario('follow-up save', {
    modules: ['followups-form.js', 'followups-actions.js'],
    fields: {
      'fu-content': { value: 'AUDIT-A: typed while A was open' },
      'fu-index': { value: '-1' },
      'fu-method': { value: 'Email' },
      'fu-status': { value: 'pending' },
      'fu-date': { value: '' },
      'fu-response': { value: '' },
      'fu-feedback': { value: '' },
      'fu-next': { value: '' },
      'fu-next-date': { value: '' },
      'fu-save-btn': { disabled: false, dataset: {}, textContent: '' },
    },
    run: context => context.saveFollowUp(),
    countsWhenCurrent: true,
  }),
  scenario('follow-up archive', {
    modules: ['followups-form.js', 'followups-actions.js'],
    fields: {},
    run: context => context.archiveFollowUp(0),
    countsWhenCurrent: true,
  }),
  scenario('after-sales archive', {
    modules: ['followups-form.js', 'aftersales-actions.js'],
    fields: {},
    run: context => context.archiveAfterSales(0),
    countsWhenCurrent: true,
  }),
  scenario('attachment archive', {
    modules: ['followups-form.js', 'files-actions.js'],
    fields: {},
    run: context => context.archiveAttachment(0),
  }),
  scenario('pre-sales task save', {
    modules: ['followups-form.js', 'sampling-actions.js'],
    fields: {
      'sample-task-index': { value: '-1' },
      'sample-task-save': { disabled: false },
    },
    run: context => context.saveSampleTask(),
    countsWhenCurrent: true,
  }),
];

(async () => {
  for (const item of scenarios) {
    const { name, context, loads, calls, seen } = item;
    context.State.currentInquiry = lead('A');
    const action = item.run(context);

    // The reader gives up on the form and opens somebody else.
    seen.generation += 1;
    context.State.currentInquiry = lead('B');
    loads.A.resolve(lead('A'));
    await action;

    assert.strictEqual(context.State.currentInquiry.id, 'B',
      `${name}: the panel now belongs to A`);
    assert.strictEqual(context.State.currentInquiry.follow_ups[0].content,
      'B follow-up', `${name}: B's panel carries A's follow-up`);
    assert.strictEqual(seen.renders, 0, `${name}: repainted B's panel`);
    assert.strictEqual(seen.tabs, 0, `${name}: moved B's tabs`);
    assert.strictEqual(seen.hides, 0, `${name}: closed B's form`);
    assert.strictEqual(seen.notes, 0, `${name}: reported the save over B`);
    assert.strictEqual(seen.counts, 0, `${name}: reloaded B's module list`);
    assert.deepStrictEqual(seen.alerts, [], `${name}: alerted: ${seen.alerts}`);
    // The write itself happened. An action that would have moved a navigation
    // number still owes the reader that number; nothing else about their panel.
    if (item.countsWhenCurrent) {
      assert.ok(seen.navOnly >= 1, `${name}: the navigation counts were not refreshed`);
    }
    assert.ok(calls.length >= 1, `${name}: nothing was written`);
    // Whatever it wrote, it must not have been written against B: the reader
    // never asked for anything on the customer they had just opened.
    assert.ok(!JSON.stringify(calls).includes('"B"'),
      `${name}: the write landed on the newly opened customer: ${JSON.stringify(calls)}`);
  }

  // A05 · the same customer, a later visit. Open A, start saving, look at B,
  // come back to A: the customer id matches again, so an id-only check would
  // hand A's older answer to the panel the reader has since re-typed into.
  const revisit = scenario('follow-up save, then A again', {
    modules: ['followups-form.js', 'followups-actions.js'],
    fields: {
      'fu-content': { value: 'typed on the first visit' },
      'fu-index': { value: '-1' },
      'fu-method': { value: 'Email' },
      'fu-status': { value: 'pending' },
      'fu-date': { value: '' },
      'fu-response': { value: '' },
      'fu-feedback': { value: '' },
      'fu-next': { value: '' },
      'fu-next-date': { value: '' },
      'fu-save-btn': { disabled: false, dataset: {}, textContent: '' },
    },
    run: context => context.saveFollowUp(),
  });
  revisit.context.State.currentInquiry = lead('A');
  const firstVisit = revisit.run(revisit.context);
  revisit.seen.generation += 1;
  revisit.context.State.currentInquiry = lead('B');
  revisit.seen.generation += 1;
  const secondVisitLead = { ...lead('A'), stage: 'Quoted' };
  revisit.context.State.currentInquiry = secondVisitLead;
  revisit.loads.A.resolve({ ...lead('A'), stage: 'Following' });
  await firstVisit;
  assert.strictEqual(revisit.context.State.currentInquiry, secondVisitLead,
    'the older visit to the same customer overwrote the newer one');
  assert.strictEqual(revisit.context.State.currentInquiry.stage, 'Quoted',
    'a stale answer replaced the panel the reader had re-opened');
  assert.strictEqual(revisit.seen.renders, 0, 'the re-opened panel was redrawn');
  assert.strictEqual(revisit.seen.hides, 0, 'the re-opened form was closed');

  // A07 · written, then the screen could not be brought up to date. That is
  // not a failed save, and must never invite recording the same thing twice.
  const refreshBroke = scenario('save lands, refresh fails', {
    modules: ['followups-form.js', 'followups-actions.js'],
    fields: {
      'fu-content': { value: 'landed' },
      'fu-index': { value: '-1' },
      'fu-method': { value: 'Email' },
      'fu-status': { value: 'pending' },
      'fu-date': { value: '' },
      'fu-response': { value: '' },
      'fu-feedback': { value: '' },
      'fu-next': { value: '' },
      'fu-next-date': { value: '' },
      'fu-save-btn': { disabled: false, dataset: {}, textContent: '' },
    },
    run: context => context.saveFollowUp(),
  });
  refreshBroke.context.State.currentInquiry = lead('A');
  const landing = refreshBroke.run(refreshBroke.context);
  refreshBroke.loads.A.reject(new Error('re-read failed'));
  await landing;
  assert.deepStrictEqual(refreshBroke.seen.alerts, [],
    `a successful save was reported as an error: ${refreshBroke.seen.alerts}`);
  assert.ok(refreshBroke.seen.notices.some(text => /saved/i.test(text)
    && /not.*refresh/i.test(text)),
    `nothing said the save landed but the screen did not: ${refreshBroke.seen.notices}`);
  assert.ok(!refreshBroke.seen.notices.some(text => /error saving/i.test(text)),
    'the reader was told the save failed, which invites a second one');

  // A08 · the write itself failed while the reader was elsewhere. Recorded,
  // but not thrown across the panel they are working in now.
  const failedAway = scenario('write fails after moving on', {
    modules: ['followups-form.js', 'followups-actions.js'],
    fields: {
      'fu-content': { value: 'never landed' },
      'fu-index': { value: '-1' },
      'fu-method': { value: 'Email' },
      'fu-status': { value: 'pending' },
      'fu-date': { value: '' },
      'fu-response': { value: '' },
      'fu-feedback': { value: '' },
      'fu-next': { value: '' },
      'fu-next-date': { value: '' },
      'fu-save-btn': { disabled: false, dataset: {}, textContent: '' },
    },
    run: context => context.saveFollowUp(),
  });
  failedAway.context.State.currentInquiry = lead('A');
  failedAway.context.ApiClient = new Proxy({}, { get: () => () =>
    Promise.reject(new Error('the server refused it')) });
  const doomed = failedAway.run(failedAway.context);
  failedAway.seen.generation += 1;
  failedAway.context.State.currentInquiry = lead('B');
  await doomed;
  assert.deepStrictEqual(failedAway.seen.alerts, [],
    'a failure from an abandoned form blocked the panel in front of the reader');
  assert.ok(failedAway.seen.notices.some(text => /could not be saved/i.test(text)),
    `the failure was swallowed with no trace: ${failedAway.seen.notices}`);
  assert.strictEqual(failedAway.seen.renders, 0);

  // And the ordinary case still works: the reader is still on A when it lands.
  const still = scenarios[0];
  const solo = scenario('follow-up save, reader still on A', {
    modules: ['followups-form.js', 'followups-actions.js'],
    fields: {
      'fu-content': { value: 'stays on A' },
      'fu-index': { value: '-1' },
      'fu-method': { value: 'Email' },
      'fu-status': { value: 'pending' },
      'fu-date': { value: '' },
      'fu-response': { value: '' },
      'fu-feedback': { value: '' },
      'fu-next': { value: '' },
      'fu-next-date': { value: '' },
      'fu-save-btn': { disabled: false, dataset: {}, textContent: '' },
    },
    run: context => context.saveFollowUp(),
  });
  solo.context.State.currentInquiry = lead('A');
  const running = solo.run(solo.context);
  solo.loads.A.resolve({ ...lead('A'), stage: 'Quoted' });
  await running;
  assert.strictEqual(solo.context.State.currentInquiry.stage, 'Quoted',
    'a response the reader is waiting for must be applied');
  assert.strictEqual(solo.seen.renders, 1, 'the panel was not redrawn');
  assert.strictEqual(solo.seen.notes, 1, 'the save was not reported');
  assert.strictEqual(solo.seen.hides, 1, 'the form was left open');
  assert.strictEqual(solo.seen.counts, 1, 'the lists were not refreshed');
  void still;
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


def main() -> None:
    result = subprocess.run(
        ["node", "-e", HARNESS],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: a late panel action leaves the newly opened customer alone")


if __name__ == "__main__":
    main()
