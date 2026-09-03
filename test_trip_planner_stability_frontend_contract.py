"""Runtime contracts for Trip Planner date, draft, and region isolation.

Run:
    python test_trip_planner_stability_frontend_contract.py

The Node harness uses no browser or network access.  It executes the shipped
frontend modules in isolated VM contexts and repeats date checks under widely
separated time zones.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _node_json(script: str) -> str:
    """Run a node script and return its last line, which must be JSON."""
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, check=True, text=True,
        capture_output=True,
    )
    return result.stdout.strip().splitlines()[-1]


def _run_node(script: str, *, timezone: str | None = None) -> None:
    env = os.environ.copy()
    if timezone:
        env["TZ"] = timezone
    subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
    )


def check_static_contract() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    trip_form = (MODULES / "trip-form.js").read_text(encoding="utf-8")
    stage_filters = (MODULES / "stage-filters.js").read_text(encoding="utf-8")
    visit_state = (MODULES / "trip-visit-state.js").read_text(encoding="utf-8")
    visit_view = (MODULES / "trip-planner.js").read_text(encoding="utf-8")
    visit_actions = (MODULES / "trip-visit-actions.js").read_text(encoding="utf-8")
    itinerary_actions = (MODULES / "trip-itinerary-actions.js").read_text(encoding="utf-8")
    export_actions = (MODULES / "trip-export-actions.js").read_text(encoding="utf-8")

    assert 'id="trip-candidate-region"' in index
    assert 'id="trip-plan-region"' in index
    assert 'id="trip-region"' not in index, "the old shared region control must not return"
    assert "getElementById('trip-candidate-region')" in trip_form
    assert "getElementById('trip-plan-region')" in trip_form
    assert "setInputValue('trip-plan-region'" in trip_form
    assert "trip-candidate-region" in stage_filters and "trip-region" not in stage_filters

    assert "Date.UTC" in visit_state
    assert "getUTCFullYear" in visit_state and "getUTCDate" in visit_state
    assert "toISOString" not in visit_state, "calendar-only dates must not cross a local/UTC conversion"

    assert "function refreshVisitCard" in visit_view
    assert "refreshVisitCard" in visit_actions
    assert "renderVisitExecution(State.currentTripPlan)" not in visit_actions, (
        "saving one visit must not rebuild every card and discard sibling drafts"
    )
    assert index.index("trip-itinerary-actions.js") < index.index("trip-export-actions.js")

    # One definition of the download entry point, and it carries the version.
    # A second one that took only the format would silently turn the shared
    # download into the copy that holds visit preparation, and which one won
    # would depend on the order the page happens to load its scripts in.
    definitions = [
        path.name
        for path in (ROOT / "frontend/js/modules").glob("*.js")
        if "window.exportCurrentTripPlan" in path.read_text(encoding="utf-8")
    ]
    assert definitions == ["trip-export-actions.js"], (
        f"the download entry point is defined in {definitions}"
    )
    assert "window.exportCurrentTripPlan = download;" in export_actions

    naming = _source("frontend/js/modules/trip-export-naming.js")
    assert "summary.stale === true || summary.valid === false" in naming
    assert "before exporting" in naming
    assert "blockedReason" in export_actions, (
        "the panel no longer asks why a download would be refused"
    )


def check_calendar_dates_are_timezone_invariant() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = {
    console,
    Date,
    TripPlanIdentity: { intend: () => 1,
        accept(token, plan) { context.State.currentTripPlan = plan; return true; },
        clear() { context.State.currentTripPlan = null; return true; },
        isCurrent: () => true },
    State: { currentTripPlan: null },
    JPTRender: { escape: value => String(value ?? '') },
    TripPlannerModule: { renderVisitExecution() {} },
};
context.window = context;
vm.createContext(context);
vm.runInContext(
    fs.readFileSync('frontend/js/modules/trip-visit-state.js', 'utf8'),
    context,
    { filename: 'trip-visit-state.js' }
);

assert.strictEqual(context.TripVisitState.normalizeDay('2026-09-15'), '2026-09-15');
assert.strictEqual(context.TripVisitState.normalizeDay('2026-02-30'), '');
assert.strictEqual(context.TripVisitState.addDay('2026-09-30'), '2026-10-01');
assert.deepStrictEqual(
    Array.from(context.TripVisitState.planDays({
        stops: [
            { planned_date: '2026-09-15', planned_end_date: '2026-09-17' },
            { planned_date: '2026-09-15T23:30:00+14:00', planned_end_date: null },
        ],
    })),
    ['2026-09-15', '2026-09-16', '2026-09-17']
);
assert.strictEqual(
    context.TripVisitState.stopMatchesDay(
        { planned_date: '2026-09-15', planned_end_date: '2026-09-17' },
        '2026-09-15'
    ),
    true
);
"""
    for timezone in (
        "Pacific/Kiritimati",  # UTC+14: exposed the former previous-day conversion
        "Asia/Shanghai",
        "Europe/Berlin",
        "America/Los_Angeles",
    ):
        _run_node(script, timezone=timezone)


def check_region_state_and_sibling_visit_draft_are_preserved() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const elements = new Map();
function input(id, value = '', extra = {}) {
    const element = { id, value, checked: false, files: [], ...extra };
    elements.set(id, element);
    return element;
}

input('trip-candidate-region', 'AM');
input('trip-plan-region', 'EU');
input('trip-stage', 'Quoted');
input('trip-title', 'Europe September');
input('trip-start-date', '2026-09-15');
input('trip-end-date', '2026-09-30');
input('trip-origin-name', 'Shanghai');
input('trip-origin-lat', '31.2304');
input('trip-origin-lng', '121.4737');
input('trip-destination-name', 'Shanghai');
input('trip-destination-lat', '31.2304');
input('trip-destination-lng', '121.4737');
input('trip-travel-mode', 'flight');
input('trip-avoid-weekends', '', { checked: true });
input('trip-holidays', '2026-09-21');
input('trip-description', 'Customer visits');

const stopAFields = {
    status: input('visit-status-a', 'Follow-up Needed'),
    result: input('visit-result-a', 'Saved meeting note'),
    needs: input('visit-needs-a', 'Saved needs'),
    competitor: input('visit-competitor-a', 'Saved competitor'),
    budget: input('visit-budget-a', '100000'),
    decision: input('visit-decision-a', 'CTO'),
    next: input('visit-next-a', 'Send sample'),
    due: input('visit-due-a', '2026-09-22'),
    sample: input('visit-sample-a', 'yes'),
    quote: input('visit-quote-a', 'no'),
    actualDate: input('visit-actual-date-a', '2026-09-21'),
    actualPeriod: input('visit-actual-period-a', 'PM'),
};
const siblingDraft = {
    result: input('visit-result-b', 'UNSAVED sibling meeting note'),
    needs: input('visit-needs-b', 'UNSAVED sibling needs'),
    next: input('visit-next-b', 'UNSAVED sibling next action'),
    file: input('visit-file-b', '', { files: [{ name: 'unsaved-evidence.pdf' }] }),
};
const savedCard = { outerHTML: '' };
elements.set('visit-card-a', savedCard);

let capturedPayload = null;
let fullVisitRenderCount = 0;
const serverPlan = {
    id: 'plan-1',
    row_version: 8,
    stops: [
        {
            id: 'a', row_version: 4, sequence_no: 1, customer_name: 'Alpha',
            result_status: 'Follow-up Needed', result_notes: 'Saved meeting note',
            visit_customer_needs: 'Saved needs', visit_next_action: 'Send sample',
            visit_followup_due_date: '2026-09-22', visit_sample_needed: true,
        },
        {
            id: 'b', row_version: 2, sequence_no: 2, customer_name: 'Beta',
            result_status: 'Planned', result_notes: 'SERVER old sibling note',
            visit_customer_needs: 'SERVER old sibling needs',
            visit_next_action: 'SERVER old sibling action',
        },
    ],
};

const context = {
    console,
    Date,
    TripPlanIdentity: { intend: () => 1,
        accept(token, plan) { context.State.currentTripPlan = plan; return true; },
        clear() { context.State.currentTripPlan = null; return true; },
        isCurrent: () => true },
    State: {
        tripBusy: false,
        tripCandidatePagination: { limit: 25, offset: 0 },
        currentTripPlan: {
            id: 'plan-1', row_version: 7,
            stops: [{ id: 'a', row_version: 3 }, { id: 'b', row_version: 2 }],
        },
    },
    document: { getElementById: id => elements.get(id) || null,
              querySelectorAll: () => [] },
    ApiClient: {
        async updateTripStop(planId, stopId, payload) {
            assert.strictEqual(planId, 'plan-1');
            assert.strictEqual(stopId, 'a');
            capturedPayload = payload;
            return serverPlan;
        },
    },
    I18n: { t: value => value },
    JPTRender: {
        escape: value => String(value ?? ''),
        field: (label, value) => `<div>${label}:${value ?? ''}</div>`,
        empty: value => value,
    },
    notify() {},
    alert(message) { throw new Error(`unexpected alert: ${message}`); },
    setTripBusy(value) { context.State.tripBusy = value; },
    async handleTripError(error) { throw error; },
    renderCurrentTripPlan() {},
    renderTripMap() {},
    downloadBlob() {},
};
context.window = context;
vm.createContext(context);
vm.runInContext(
    fs.readFileSync('frontend/js/modules/trip-form.js', 'utf8'),
    context,
    { filename: 'trip-form.js' }
);
vm.runInContext(
    fs.readFileSync('frontend/js/modules/trip-stop-duration-payload.js', 'utf8'),
    context,
    { filename: 'trip-stop-duration-payload.js' }
);

const filters = vm.runInContext('getTripFilters()', context);
const planPayload = vm.runInContext('readTripPlanFormPayload()', context);
assert.strictEqual(filters.region, 'AM');
assert.strictEqual(planPayload.region, 'EU');
vm.runInContext("populateTripPlanForm({ region: 'SEA' })", context);
assert.strictEqual(elements.get('trip-candidate-region').value, 'AM');
assert.strictEqual(elements.get('trip-plan-region').value, 'SEA');

context.TripVisitState = {
    escape: value => String(value ?? ''),
    planDays: () => [],
    currentDateForPlan: () => '',
    stopMatchesDay: () => true,
    customerPersonnelLine: () => '',
    channelPartnerLine: () => '',
    internalParticipantsLine: () => '',
    agendaLine: stop => (stop && stop.visit_purpose) || '',
    addressLine: () => '',
    getSelectedDate: () => '',
};
vm.runInContext(
    fs.readFileSync('frontend/js/modules/trip-planner.js', 'utf8'),
    context,
    { filename: 'trip-planner.js' }
);
const originalRender = context.TripPlannerModule.renderVisitExecution;
context.TripPlannerModule.renderVisitExecution = plan => {
    fullVisitRenderCount += 1;
    return originalRender(plan);
};
vm.runInContext(
    fs.readFileSync('frontend/js/modules/trip-visit-answer.js', 'utf8'),
    context,
    { filename: 'trip-visit-answer.js' }
);
vm.runInContext(
    fs.readFileSync('frontend/js/modules/trip-visit-actions.js', 'utf8'),
    context,
    { filename: 'trip-visit-actions.js' }
);

(async () => {
    await context.TripPlannerModule.saveVisitExecution('a');
    assert(capturedPayload, 'saved card payload was not sent');
    assert.strictEqual(capturedPayload.result_notes, 'Saved meeting note');
    assert.strictEqual(capturedPayload.visit_next_action, 'Send sample');
    assert.strictEqual(capturedPayload.visit_followup_due_date, '2026-09-22');
    assert.strictEqual(capturedPayload.visit_sample_needed, true);
    assert.strictEqual(capturedPayload.visit_quote_needed, false);
    assert.strictEqual(capturedPayload.actual_visit_date, '2026-09-21');
    assert.strictEqual(capturedPayload.actual_visit_period, 'PM');
    assert.strictEqual(savedCard.outerHTML.includes('Saved meeting note'), true);
    assert.strictEqual(fullVisitRenderCount, 0, 'saving one card rebuilt the whole visit list');
    assert.strictEqual(siblingDraft.result.value, 'UNSAVED sibling meeting note');
    assert.strictEqual(siblingDraft.needs.value, 'UNSAVED sibling needs');
    assert.strictEqual(siblingDraft.next.value, 'UNSAVED sibling next action');
    assert.strictEqual(siblingDraft.file.files[0].name, 'unsaved-evidence.pdf');
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
"""
    _run_node(script)


def check_free_stop_payload_carries_no_undeclared_field() -> None:
    """The personal-stop endpoints forbid extra fields too.

    The itinerary check below existed and this one did not, so a field added to
    the personal-stop form reached the browser as a 422 on every save. One
    endpoint having a guard says nothing about the next one: every request model
    the frontend builds a payload for needs the same comparison.
    """
    import re

    router = _source("backend/routers/review.py")
    declared = set()
    for name in ("TripFreeStopCreate", "TripFreeStopUpdate"):
        block = router[router.index(f"class {name}(BaseModel)"):]
        block = block[:block.index("\n\n\nclass ")]
        assert 'extra="forbid"' in block, (
            f"this check exists because {name} forbids extra fields"
        )
        declared |= set(re.findall(r"^    (\w+):", block, re.M))

    sent = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const values = {
  'trip-free-stop-category': 'hotel', 'trip-free-stop-name': 'Stuttgart',
  'trip-free-stop-stay': '4', 'trip-free-stop-lat': '48.7758',
  'trip-free-stop-lng': '9.1829', 'trip-free-stop-period': 'auto',
  'trip-free-stop-confirmation': 'confirmed',
  'trip-free-stop-start-date': '2026-09-05',
  'trip-free-stop-start-period': 'AM',
};
const people = [{ value: 'u1' }];
const context = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: value => value },
  TripDuration: { parseDisplayDays: value => Math.round(Number(value) * 2),
                  toDisplayDays: value => String(value / 2),
                  readStopDuration: () => 2 },
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: { id: 'p1', planning_mode: 'team', stops: [],
                              members: [{ user_id: 'u1', display_name: 'A' }] } },
  document: { getElementById: id => id === 'trip-free-stop-people-list'
    ? { set innerHTML(_) {}, querySelectorAll: () => people }
    : { value: values[id] ?? '', hidden: false } },
};
context.window = context; vm.createContext(context);
for (const file of ['trip-free-stop-team-controls.js', 'trip-free-stop-form.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
console.log(JSON.stringify(Object.keys(context.TripFreeStopForm.payload())));
"""))
    undeclared = sorted(set(sent) - declared)
    assert not undeclared, (
        "the personal-stop request carries fields the endpoint rejects, so "
        f"every save fails with 422: {undeclared}"
    )
    assert "planned_date" in sent, (
        "the check is only meaningful while the form sends the stay day"
    )


def check_itinerary_payload_carries_no_undeclared_field() -> None:
    """The itinerary endpoints forbid extra fields, so the payload must match them.

    A field added to the plan header spreads into the preview and save requests
    through readTripPlanFormPayload. TripItineraryGenerate is declared with
    extra="forbid", so one stray field makes every preview and every save fail
    with 422 - not the field's own feature, the whole route calculation.
    """
    import re

    router = _source("backend/routers/review.py")
    block = router[router.index("class TripItineraryGenerate"):]
    block = block[:block.index("\n\n\nclass ")]
    assert 'extra="forbid"' in block, (
        "this check exists because the schema forbids extra fields"
    )
    declared = set(re.findall(r"^    (\w+):", block, re.M))

    sent = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const elements=new Map();
[
 'trip-title','trip-start-date','trip-end-date','trip-plan-region',
 'trip-planning-mode','trip-origin-name','trip-origin-lat','trip-origin-lng',
 'trip-destination-name','trip-destination-lat','trip-destination-lng',
 'trip-holidays','trip-description','trip-avoid-weekends',
 'trip-route-order-mode','trip-travel-mode','trip-departure-window-start',
 'trip-departure-window-end','trip-return-window-start','trip-return-window-end',
].forEach(id => elements.set(id, { id, value: '', checked: false }));
elements.get('trip-planning-mode').value = 'team';
const context = {
  console, Date,
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: { id: 'p1', stops: [] },
           tripCandidatePagination: { limit: 25, offset: 0 } },
  document: { getElementById: id => elements.get(id) || null,
              querySelectorAll: () => [] },
  I18n: { t: value => value },
  toDateInput: () => '2026-09-15', formatDate: value => value,
};
context.window = context; vm.createContext(context);
for (const file of ['trip-form.js', 'trip-stop-duration-payload.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
console.log(JSON.stringify(Object.keys(context.readTripItineraryPayload())));
"""))
    undeclared = sorted(set(sent) - declared)
    assert not undeclared, (
        "the itinerary request carries fields the endpoint rejects, so preview "
        f"and save both fail with 422: {undeclared}"
    )
    # And the plan header request still carries the mode, which it owns.
    header = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const elements=new Map();
['trip-title','trip-planning-mode','trip-avoid-weekends','trip-holidays']
  .forEach(id => elements.set(id, { id, value: '', checked: false }));
elements.get('trip-planning-mode').value = 'team';
const context = { console, Date,
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: { id: 'p1', stops: [] },
           tripCandidatePagination: { limit: 25, offset: 0 } },
  document: { getElementById: id => elements.get(id) || null,
              querySelectorAll: () => [] },
  I18n: { t: value => value }, toDateInput: () => '2026-09-15',
  formatDate: value => value };
context.window = context; vm.createContext(context);
for (const file of ['trip-form.js', 'trip-stop-duration-payload.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
console.log(JSON.stringify(context.readTripPlanFormPayload()));
"""))
    assert header.get("planning_mode") == "team", (
        f"creating or updating a plan must still carry the mode: {header}"
    )


JS_LOCK_BOX = r'''
const fs=require('fs');const vm=require('vm');
const context = { console, escapeHtml: value => String(value ?? ''),
  I18n: { t: key => String(key) },
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: {}, TripPlanningDraft: { get: () => ({ routeOrderMode: 'auto' }) } };
context.window = context; vm.createContext(context);
vm.runInContext(
  fs.readFileSync('frontend/js/modules/trip-stop-schedule-controls.js', 'utf8'),
  context,
);
const blank = context.TripStopScheduleControls.render({
  id: 's1', planned_date: null, planned_start_period: null,
  schedule_locked: 0, preferred_period: 'auto',
  confirmation_status: 'unconfirmed' });
const agreed = context.TripStopScheduleControls.render({
  id: 's1', planned_date: '2026-09-04', planned_start_period: 'PM',
  schedule_locked: 1, preferred_period: 'auto',
  confirmation_status: 'unconfirmed' });
const box = /id="stop-schedule-lock-s1"[^>]*/;
console.log(JSON.stringify({
  disabledWithoutDate: /disabled/.test(blank.match(box)[0]),
  checkedWhenAgreed: /checked/.test(agreed.match(box)[0]),
  agreedMarker: agreed.includes('is-agreed'),
}));
'''


def check_agreed_visit_time_can_be_entered() -> None:
    """The time a customer agreed to must be typeable, and must be sent.

    The calculation reads a locked visit's time from the stop, so the whole
    "plan around the times I agreed" workflow depends on the UI being able to
    put one there. Everything behind it existed while the only date field on
    screen was read-only and labelled "calculated by route preview", which made
    the feature unreachable - so what is checked here is the input itself.
    """
    controls = _source("frontend/js/modules/trip-stop-schedule-controls.js")
    assert "readonly" not in controls, (
        "the agreed date has to be editable"
    )
    assert "stop-agreed-date-" in controls and "stop-agreed-period-" in controls, (
        "there must be an input for the agreed date and its AM/PM period"
    )
    view = _source("frontend/js/modules/trip-itinerary-view.js")
    assert "Calculated by route preview" not in view, (
        "the read-only calculated date must not sit beside the editable one"
    )

    sent = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const values = {
  'stop-agreed-date-s1': '2026-09-16',
  'stop-agreed-period-s1': 'AM',
  'stop-period-s1': 'auto',
  'stop-confirmation-s1': 'confirmed',
};
const nodes = new Map(Object.entries(values).map(([id, value]) => [id, { id, value }]));
nodes.set('stop-schedule-lock-s1', { id: 'lock', checked: true, disabled: false });
const context = {
  console,
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: { id: 'p1', route_order_mode: 'auto' } },
  document: { getElementById: id => nodes.get(id) || null,
              querySelectorAll: () => [] },
  I18n: { t: value => value }, escapeHtml: value => String(value ?? ''),
};
context.window = context; vm.createContext(context);
vm.runInContext(
  fs.readFileSync('frontend/js/modules/trip-stop-schedule-controls.js', 'utf8'),
  context,
);
console.log(JSON.stringify(context.TripStopScheduleControls.readPayload('s1')));
"""))
    assert sent["planned_date"] == "2026-09-16", sent
    assert sent["planned_start_period"] == "AM", sent
    assert sent["schedule_locked"] is True, (
        f"confirming the time must lock it, or the route will move it: {sent}"
    )

    # The box must be usable straight away. Waiting for the date to be saved
    # first meant typing a date, waiting, and coming back to tick a box that
    # had been greyed out - which reads as a box that cannot be ticked at all.
    rendered = json.loads(_node_json(JS_LOCK_BOX))
    assert rendered["disabledWithoutDate"] is False, (
        "the confirm box must be usable before the date has been saved"
    )
    assert rendered["checkedWhenAgreed"] is True
    assert rendered["agreedMarker"] is True, (
        "an agreed time needs a visible mark, not only a ticked box"
    )

    # An agreed time is a fact, so it is saved rather than left in the draft:
    # the calculation reads it from the stop, not from the preview payload.
    actions = _source("frontend/js/modules/trip-stop-appointment-actions.js")
    assert "updateTripStop" in actions, (
        "the agreed time must be saved, not only put in the route draft"
    )
    index = _source("frontend/index.html")
    assert "trip-stop-appointment-actions.js" in index, "module never loaded"


def check_planning_mode_is_saved_not_drafted() -> None:
    """Switching how a plan is planned has to reach the server.

    The mode decides which calculation runs and which panels belong on screen.
    Kept only in the route draft it never reached the plan, so switching back to
    one traveller left the team panels up and the next save still refused the
    plan for having no team members.
    """
    route_form = _source("frontend/js/modules/trip-route-form.js")
    assert "'trip-planning-mode'" not in route_form, (
        "the mode is a plan setting, not one of the route draft's fields"
    )
    index = _source("frontend/index.html")
    assert 'id="trip-planning-mode"' in index
    select = index[index.index('id="trip-planning-mode"'):]
    select = select[:select.index(">")]
    assert "TripPlanningModeActions.planningModeChanged()" in select, (
        f"changing the mode must save it: {select}"
    )
    actions = _source("frontend/js/modules/trip-stop-appointment-actions.js")
    assert "updateTripPlan" in actions and "planning_mode" in actions, (
        "the mode must be sent to the plan endpoint"
    )
    # The panels follow the saved plan, so saving is what makes them appear and
    # disappear; nothing may read the mode off the form instead.
    for module in ("trip-team-view.js", "trip-schedule-view.js",
                   "trip-flexible-suggestions.js"):
        source = _source(f"frontend/js/modules/{module}")
        assert "trip-planning-mode" not in source, (
            f"{module} must read the saved mode, not the form control"
        )


def check_assets_are_stamped_with_the_build() -> None:
    """Every asset URL must change when the build does.

    The version markers in index.html were written by hand, so a module whose
    contents changed kept the same URL and browsers went on using the copy they
    already had. That shows up as a half-updated page - a new label from one
    module beside old behaviour from another - which is very hard to tell apart
    from a bug in the feature itself.
    """
    import os
    import re
    import sys
    import tempfile

    os.environ["JPT_DATA_DIR"] = tempfile.mkdtemp(prefix="jpt_asset_stamp_")
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient

    from backend.config import APP_VERSION, init_settings
    from backend.startup_upgrade import initialize_database_safely

    initialize_database_safely(init_settings(ROOT))
    from backend.app_v2 import create_app

    client = TestClient(create_app())
    # Every route that can return the page, not only the root: the copy on disk
    # still holds the hand-written markers, and asking for it by name used to
    # send it straight through - which handed the browser exactly the asset URLs
    # it already had cached.
    for route in ("/", "/index.html", "/some/spa/route"):
        html = client.get(route).text
        stamps = set(re.findall(r'/static/[^"?]+\?v=([^"]+)', html))
        assert len(stamps) == 1, (
            f"{route}: assets must all carry one build stamp, found "
            f"{sorted(stamps)}"
        )
        stamp = next(iter(stamps))
        assert APP_VERSION in stamp, (
            f"{route}: the stamp must change with the version: {stamp}"
        )
        assert not re.search(r'\?v=\d+\.\d+"', html), (
            f"{route}: a hand-written version marker survived"
        )


def check_opening_visit_preparation_reveals_the_editor() -> None:
    """The visit preparation editor is brought to whoever opened it.

    The editor is one panel inside the daily schedule, and the buttons that open
    it are spread down the page - visit execution is a whole panel below it. It
    was opening correctly and off-screen, so the button read as broken; pressing
    it a second time hit an early return and did even less.
    """
    calls = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const scrolls = [];
const editor = {
  hidden: true, innerHTML: '',
  scrollIntoView: () => scrolls.push('scrolled'),
  closest: () => ({ classList: { toggle() {} } }),
  setAttribute() {},
};
const context = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: value => value },
  document: { getElementById: id =>
    id === 'trip-briefing-editor' ? editor : null },
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: { id: 'p1' } },
  TripBriefingDraft: {
    getStopId: () => 'stop-1', guard: () => false, reset() {},
    confirmDiscard: () => true,
  },
  ApiClient: {}, TripBriefingForm: {},
};
context.window = context; vm.createContext(context);
for (const file of ['trip-briefing-reveal.js', 'trip-briefing-actions.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
// The stop already loaded: no request to make, but the reader must still be
// taken to the panel rather than left looking at the button.
context.TripBriefingActions.open('stop-1');
const afterReopen = scrolls.length;
context.TripBriefingActions.close({ force: true });
const afterClose = scrolls.length;
console.log(JSON.stringify({ afterReopen, afterClose, hidden: editor.hidden }));
"""))
    assert calls["afterReopen"] == 1, (
        "opening the preparation of a visit already loaded must still bring the "
        f"editor into view: {calls}"
    )
    assert calls["afterClose"] == 1, (
        f"closing the editor must not scroll anywhere: {calls}"
    )
    assert calls["hidden"] is True, "closing must hide the editor"


def check_editing_a_visit_keeps_the_readers_place() -> None:
    """Adding or removing a row does not throw the reader back to the top.

    Every button in the preparation editor rebuilds the whole form, and a
    rebuilt element starts at scroll zero. In a panel taller than the window
    that means each click scrolls away from the thing the click just did, and
    the reader has to find their way back before they can type.
    """
    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const focused = [];
let pane = null;
function makePane() {
  pane = { scrollTop: 0, className: 'trip-briefing-scroll' };
  return pane;
}
const field = {
  scrollIntoView: () => focused.push('scrolled'),
  focus: () => focused.push('focused'),
};
const root = {
  hidden: true, _html: '',
  set innerHTML(value) { this._html = value; makePane(); },
  get innerHTML() { return this._html; },
  querySelector: selector =>
    selector === '.trip-briefing-scroll' ? pane : null,
};
const context = {
  console,
  document: {
    getElementById: id => id === 'trip-briefing-editor' ? root : null,
    querySelectorAll: () => [{ querySelector: () => field }],
  },
};
context.window = context; vm.createContext(context);
vm.runInContext(
  fs.readFileSync('frontend/js/modules/trip-briefing-scroll.js', 'utf8'), context);
const api = context.TripBriefingScroll;

api.replace(root, '<div class="trip-briefing-scroll"></div>');
pane.scrollTop = 420;                       // the reader scrolled down
api.replace(root, '<div class="trip-briefing-scroll"></div>');   // a row is added
const kept = pane.scrollTop;
api.focusRow('participants', 0);
console.log(JSON.stringify({ kept, focused }));
"""))
    assert data["kept"] == 420, (
        "redrawing the editor must leave the reader where they were, not at the "
        f"top: {data['kept']}"
    )
    assert data["focused"] == ["scrolled", "focused"], (
        f"a newly added row must be brought to the reader and focused: {data['focused']}"
    )

    css = _source("frontend/css/style.css")
    assert "repeat(auto-fill, minmax(320px, 1fr))" in css, (
        "the rows of a section must fill the width of the panel; one column on "
        "a wide panel turns a handful of attendees into a long scroll"
    )

    saving = _source("frontend/js/modules/trip-briefing-actions.js")
    assert "TripPlanRefresh.reread(planId)" in saving, (
        "saving a visit can change who attends or where it is, and both decide "
        "the route: the plan must be re-read, not redrawn from memory - and "
        "read on its own, since a whole-planner reload stops whenever another "
        "editor is holding unsaved work"
    )
    assert "stop.briefing = Object.fromEntries" not in saving, (
        "patching the saved visit into the plan held in the browser leaves the "
        "timeline drawing the colleagues and legs of the previous calculation"
    )

    form = _source("frontend/js/modules/trip-briefing-rows.js")
    assert "TripBriefingScroll.replace(root," in form, (
        "the editor must be redrawn through the helper that keeps the place"
    )
    assert "root.innerHTML = `<div" not in form, (
        "a direct innerHTML write bypasses the scroll position"
    )


def check_plan_header_survives_a_reload() -> None:
    """The plan header shown is the one that was saved.

    Filling the form reads the header from the route draft, and the draft was
    not carrying the planning mode: every redraw put the select back to
    single-traveller, and the next header save wrote that back, turning a team
    trip solo. A renamed plan must survive the same round trip.
    """
    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const context = {
  console,
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: null, tripBusy: false },
  TripRouteValues: {
    transportPriority: () => ['flight', 'drive'],
    cleanLegOverride: value => value,
  },
  TripDuration: { readStopDuration: () => 2, normalizeHalfDays: value => value },
  document: { getElementById: () => null },
  I18n: { t: value => value },
};
context.window = context; vm.createContext(context);
for (const file of ['trip-leg-overrides.js', 'trip-planning-draft.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
const api = context.TripPlanningDraft;
const plan = { id: 'p1', title: 'Autumn Europe', planning_mode: 'team', stops: [] };

const fresh = api.hydrate(plan, {});
// The user renames the plan; only the draft knows until the next save.
api.change(draft => { draft.header = { ...draft.header, title: 'Autumn EU' }; });
const renamed = api.get();
// Something else reloads the plan - a saved visit, a new member.
const reloaded = api.hydrate(plan, {});
console.log(JSON.stringify({
  mode: fresh.header.planning_mode,
  renamedTitle: renamed.header.title,
  afterReload: reloaded.header.title,
  modeAfterReload: reloaded.header.planning_mode,
}));
"""))
    assert data["mode"] == "team", (
        "the draft header must carry the planning mode, or the form shows "
        f"single-traveller for a team trip: {data['mode']}"
    )
    assert data["modeAfterReload"] == "team", data
    assert data["renamedTitle"] == "Autumn EU", data
    assert data["afterReload"] == "Autumn EU", (
        "reloading the plan must not throw away a rename that has not been "
        f"saved yet: {data['afterReload']}"
    )


def check_applying_a_suggestion_keeps_the_airports() -> None:
    """A travel suggestion says how far and how long, never which airports.

    Applying one replaced the whole stored choice for that connection, so the
    airports the user had searched for and confirmed went with it: the fields
    emptied themselves on the click after they were filled in, and the flown leg
    stopped expanding into its drive, flight and drive.
    """
    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const draft = { legOverrides: { 'origin>x': {
  departure_airport_name: 'Shenzhen SZX',
  departure_airport_lat: 22.6393, departure_airport_lng: 113.8106,
  arrival_airport_name: 'Paris CDG',
  arrival_airport_lat: 49.0097, arrival_airport_lng: 2.5479,
  notes: 'typed by hand',
} } };
const context = {
  console,
  alert: () => {}, notify: () => {},
  I18n: { t: value => value },
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: { legs: [{ leg_key: 'origin>x' }] } },
  document: { getElementById: () => null, querySelectorAll: () => [] },
  TripDuration: {
    normalizeTravelHalfDays: v => v, fromDisplayTravelDays: v => v * 2,
  },
  TripPlanningDraft: { change: mutate => mutate(draft), get: () => draft },
  TripSuggestionState: {
    get: () => ({ suggestions: [{
      suggestion_id: 's1', leg_key: 'origin>x', mode: 'flight',
      distance_km: 9039.5, time_hours: 16.6, travel_half_days: 4,
      notes: 'from the search',
    }] }),
    stale: () => false, markApplied: () => {}, ignore: () => {},
  },
  TripSuggestionView: { render: () => {} },
  TripTransportView: { render: () => {}, legAt: () => null },
};
context.window = context; vm.createContext(context);
for (const file of ['trip-leg-airports.js', 'trip-suggestion-actions.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
context.TripSuggestionActions.apply('s1');
console.log(JSON.stringify(draft.legOverrides['origin>x']));
"""))
    assert data["departure_airport_name"] == "Shenzhen SZX", (
        f"applying a suggestion erased the departure airport: {data}"
    )
    assert data["arrival_airport_name"] == "Paris CDG", (
        f"applying a suggestion erased the arrival airport: {data}"
    )
    assert data["departure_airport_lat"] == 22.6393, data
    assert data["arrival_airport_lng"] == 2.5479, data
    assert data["selected_mode"] == "flight", (
        f"the suggestion must still set what it is for: {data}"
    )
    assert data["manual_distance_km"] == 9039.5, data
    assert data["mode_locked"] is True, (
        "an applied suggestion is a decision, so it holds its place"
    )


def check_clearing_an_airport_clears_what_belonged_to_it() -> None:
    """Removing an airport removes the transfer that only made sense with it.

    How the traveller reaches the airport, how long it takes and how long they
    wait there all describe an airport that is no longer named. Leaving them
    behind means the next flown leg through that connection silently inherits
    somebody else's taxi ride.
    """
    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const draft = { legOverrides: { 'origin>x': {
  selected_mode: 'flight',
  departure_airport_name: 'Shenzhen SZX',
  departure_airport_lat: 22.6393, departure_airport_lng: 113.8106,
  departure_airport_stay_half_days: 1,
  departure_transfer_half_days: 2, departure_transfer_mode: 'ground_public',
  departure_transfer_time_hours: 1.2,
  arrival_airport_name: 'Paris CDG',
  arrival_airport_lat: 49.0097, arrival_airport_lng: 2.5479,
  arrival_transfer_mode: 'drive',
} } };
const context = {
  console, notify: () => {},
  escapeHtml: value => String(value ?? ''),
  I18n: { t: value => value },
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: { legs: [{ leg_key: 'origin>x' }] } },
  document: { getElementById: () => null, querySelectorAll: () => [] },
  TripDuration: { parseDisplayTravelDays: v => Number(v) * 2 },
  TripPlanningDraft: { change: mutate => mutate(draft) },
  TripTransportActions: { schedulePreview: () => {} },
  TripTransportView: { legAt: () => ({ leg_key: 'origin>x' }) },
  TripLegAirportsView: { renderCandidates: () => {} },
};
context.window = context; vm.createContext(context);
vm.runInContext(
  fs.readFileSync('frontend/js/modules/trip-leg-airports.js', 'utf8'), context);
context.TripLegAirports.clear(0, 'departure');
console.log(JSON.stringify(draft.legOverrides['origin>x']));
"""))
    for field in (
        "departure_airport_name", "departure_airport_lat",
        "departure_airport_stay_half_days", "departure_transfer_half_days",
        "departure_transfer_mode", "departure_transfer_time_hours",
    ):
        assert data[field] is None, (
            f"clearing the departure airport left {field} behind: {data[field]}"
        )
    assert data["arrival_airport_name"] == "Paris CDG", (
        "clearing one end must not touch the other"
    )
    assert data["arrival_transfer_mode"] == "drive", data


def check_airport_transfer_fields_are_never_dead_controls() -> None:
    """Nothing is shown that cannot be used.

    A transfer belongs to an airport, so before one is chosen there is nothing
    to describe. Rendering the fields greyed out put four boxes on screen that
    look fillable, do nothing when clicked, and say nothing about why. Once the
    airport is set every one of them has to work.
    """
    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const context = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: (key, params = {}) =>
    String(key).replace(/\{(\w+)\}/g, (_, n) => params[n] ?? `{${n}}`) },
  TripDuration: { toDisplayTravelDays: v => String((v || 0) / 2) },
  document: { getElementById: () => null },
};
context.window = context; vm.createContext(context);
vm.runInContext(
  fs.readFileSync('frontend/js/modules/trip-leg-airports-view.js', 'utf8'), context);
const view = context.TripLegAirportsView;
const empty = view.sideBlock(0, 'departure', {}, 'Departure airport');
const set = view.sideBlock(0, 'departure', {
  departure_airport_name: 'Shenzhen SZX', departure_airport_lat: 22.6,
  departure_airport_lng: 113.8, departure_transfer_mode: 'ground_public',
  departure_transfer_time_hours: 1.2, departure_transfer_half_days: 2,
  departure_airport_stay_half_days: 1,
}, 'Departure airport');
console.log(JSON.stringify({
  emptyDisabled: (empty.match(/disabled/g) || []).length,
  emptyHasHint: empty.includes('Find the airport first'),
  emptyHasDetail: empty.includes('trip-leg-airport-detail'),
  setDisabled: (set.match(/disabled/g) || []).length,
  setHandlers: ['modeChanged', 'hoursChanged', 'transferChanged', 'stayChanged']
    .filter(name => set.includes(`TripLegAirportDurations.${name}`)),
  setKeepsMode: set.includes('value="ground_public" selected'),
}));
"""))
    assert data["emptyDisabled"] == 0, (
        "before an airport is chosen nothing may be shown as a disabled box: "
        f"{data['emptyDisabled']} found"
    )
    assert data["emptyHasDetail"] is False, (
        "the transfer fields belong to an airport that has not been chosen yet"
    )
    assert data["emptyHasHint"], (
        "say what has to happen first, rather than showing controls that do nothing"
    )
    assert data["setDisabled"] == 0, (
        f"every field must work once the airport is set: {data['setDisabled']} disabled"
    )
    assert data["setHandlers"] == [
        "modeChanged", "hoursChanged", "transferChanged", "stayChanged"
    ], (
        "how the transfer is made, how many hours, how many days and how long "
        f"the wait is must all be settable: {data['setHandlers']}"
    )
    assert data["setKeepsMode"], "a chosen transfer mode must come back selected"


def check_a_saved_airport_comes_back_after_a_reload() -> None:
    """An airport that was saved is still there when the plan is read again.

    The server keeps airports through a plain regeneration on purpose: choosing
    one is real work and must not also require locking the leg. The browser
    rebuilt its draft from the saved legs and did the opposite - it kept an
    override only when the leg was locked or had manual numbers, and then
    stripped the airport fields out of whatever survived. Saving the route and
    looking again showed empty boxes over an itinerary that had flown through
    those airports.
    """
    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const context = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: value => value },
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: null },
  document: { getElementById: () => null, querySelectorAll: () => [] },
  TripTransportView: { render: () => {}, legAt: () => null },
  TripSuggestionState: { resetForPlan: () => {} },
};
context.window = context; vm.createContext(context);
for (const file of ['trip-duration.js', 'trip-leg-airports.js',
                    'trip-leg-overrides.js', 'trip-planning-draft.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
// Exactly what the server hands back: airports saved, the leg not locked.
const plan = { id: 'p1', planning_mode: 'team', stops: [], legs: [{
  leg_key: 'origin>x', member_id: 'a', selected_mode: 'flight', mode_locked: 0,
  manual_distance_km: null, manual_time_hours: null,
  manual_travel_half_days: null, notes: null,
  departure_airport_name: '宝安国际机场',
  departure_airport_lat: 22.6393, departure_airport_lng: 113.8106,
  departure_transfer_mode: 'ground_public',
  departure_transfer_time_hours: 1.2, departure_transfer_half_days: 2,
  arrival_airport_name: '巴黎机场',
  arrival_airport_lat: 49.0097, arrival_airport_lng: 2.5479,
}] };
const draft = context.TripPlanningDraft.hydrate(plan, { committed: true });
console.log(JSON.stringify(draft.legOverrides['origin>x'] || null));
"""))
    assert data is not None, (
        "a leg with saved airports must produce a draft entry even though it "
        "is not locked: choosing an airport is the work, locking is separate"
    )
    assert data["departure_airport_name"] == "宝安国际机场", (
        f"the departure airport did not come back: {data}"
    )
    assert data["arrival_airport_name"] == "巴黎机场", data
    assert data["departure_airport_lat"] == 22.6393, data
    assert data["departure_transfer_mode"] == "ground_public", (
        f"how the airport is reached came back empty: {data}"
    )
    assert data["departure_transfer_time_hours"] == 1.2, data
    assert data["departure_transfer_half_days"] == 2, data


def check_a_preview_keeps_choices_made_on_a_team_leg() -> None:
    """Previewing does not throw away what was chosen on a member's own leg.

    Reconciling a draft against a freshly previewed plan drops overrides for
    connections that no longer exist. It worked that out by running a single
    chain through every stop - origin to the first, each to the next, the last
    home - which is one traveller's route. In team planning each member has
    their own chain, so that run describes nobody, and every choice made on a
    real leg was discarded on the next preview: a transport mode picked from
    the list came straight back empty, as did the airports.
    """
    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const context = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: value => value },
  TripPlanIdentity: { intend: () => 1,
      accept(token, plan) { context.State.currentTripPlan = plan; return true; },
      clear() { context.State.currentTripPlan = null; return true; },
      isCurrent: () => true },
  State: { currentTripPlan: null },
  document: { getElementById: () => null, querySelectorAll: () => [] },
  TripTransportView: { render: () => {}, legAt: () => null },
  TripSuggestionState: { resetForPlan: () => {} },
};
context.window = context; vm.createContext(context);
for (const file of ['trip-duration.js', 'trip-leg-airports.js',
                    'trip-leg-overrides.js', 'trip-planning-draft.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + file, 'utf8'), context);
}
// Three stops, and members whose routes each cover only some of them.
const stops = [{ id: 's1' }, { id: 's2' }, { id: 's3' }];
const legs = [
  { leg_key: 'origin>s2', member_id: 'a', selected_mode: 'flight' },
  { leg_key: 's2>s3', member_id: 'a', selected_mode: 'drive' },
  // Another member's leg, with a decision of its own on it.
  { leg_key: 'origin>s1', member_id: 'b', selected_mode: 'flight',
    mode_locked: true },
];
const plan = { id: 'p1', planning_mode: 'team', stops, legs };
const api = context.TripPlanningDraft;
api.hydrate(plan, { committed: true });
// The reader picks a way to travel on one member's leg.
api.change(draft => {
  draft.legOverrides['origin>s2'] = {
    selected_mode: 'drive', mode_locked: false,
    arrival_airport_name: 'Paris CDG', arrival_airport_lat: 49.0097,
  };
});
// The preview comes back; the draft is reconciled against it.
const after = api.hydrate(plan, {});
const kept = after.legOverrides['origin>s2'] || null;
const others = Object.keys(after.legOverrides).sort();
// Now s1 is taken off the plan while the summary still lists its leg.
const trimmed = { ...plan, stops: [{ id: 's2' }, { id: 's3' }] };
const pruned = Object.keys(api.hydrate(trimmed, {}).legOverrides).sort();
console.log(JSON.stringify({ kept, others, pruned }));
"""))
    assert data["kept"] is not None, (
        "the transport mode chosen on a member's own leg was discarded by the "
        "preview, so the list came back showing nothing was ever chosen"
    )
    assert data["kept"]["selected_mode"] == "drive", data["kept"]
    assert data["kept"]["arrival_airport_name"] == "Paris CDG", (
        f"the airport went with it: {data['kept']}"
    )
    assert "origin>s1" in data["others"], (
        "another member's leg is a real connection too and must be kept: "
        f"{data['others']}"
    )
    assert "origin>s1" not in data["pruned"], (
        "a choice made on a connection through a stop that has been removed "
        f"must go with it: {data['pruned']}"
    )
    assert "origin>s2" in data["pruned"], (
        f"the remaining member's own leg is untouched by that: {data['pruned']}"
    )
    assert "s2>s3" not in data["others"], (
        "a leg carrying only what the calculation worked out is output, not a "
        "decision: keeping it would pin every run to the one before it - "
        f"{data['others']}"
    )


def check_the_plan_list_row_matches_the_saved_plan() -> None:
    """A row in the plan list says what the plan now says.

    The list is drawn from its own copy of each plan, so saving one and
    redrawing the list left the row showing the old name, and later the old
    dates. Every field the row renders is refreshed in one place, and this
    checks the row and that place still agree on which fields those are.
    """
    import re

    data = json.loads(_node_json(r"""
const fs=require('fs');const vm=require('vm');
const context = { console, State: { tripPlans: [
  { id: 'p1', title: 'Old name', start_date: '2026-08-28',
    end_date: '2026-09-25', stop_count: 2, row_version: 7 },
  { id: 'p2', title: 'Another', start_date: '2026-10-01',
    end_date: '2026-10-09', stop_count: 1, row_version: 3 },
] } };
context.window = context; vm.createContext(context);
vm.runInContext(
  fs.readFileSync('frontend/js/modules/trip-plan-list-sync.js', 'utf8'), context);
context.syncTripPlanListEntry({
  id: 'p1', title: 'Trip Sept', start_date: '2026-09-02',
  end_date: '2026-09-30', row_version: 8, stops: [{}, {}, {}],
});
console.log(JSON.stringify(context.State.tripPlans));
"""))
    row, untouched = data
    assert row["title"] == "Trip Sept", row
    assert row["start_date"] == "2026-09-02", (
        f"the row still shows the dates the plan had before saving: {row}"
    )
    assert row["end_date"] == "2026-09-30", row
    assert row["row_version"] == 8, row
    assert row["stop_count"] == 3, row
    assert untouched["title"] == "Another", "only the saved plan's row changes"

    # The row and the refresh have to agree on which fields a row shows, so a
    # field added to the row cannot be left out of the refresh.
    listing = _source("frontend/js/modules/trip-plans.js")
    sync = _source("frontend/js/modules/trip-plan-list-sync.js")
    for field in sorted(set(re.findall(r"\bplan\.(\w+)", listing)) - {"id"}):
        assert field in sync, (
            f"the plan list shows {field}, but saving a plan never puts the new "
            "value back on the row"
        )

    for name in ("trip-itinerary-actions.js", "trip-plan-title-actions.js",
                 "trip-free-stop-actions.js"):
        source = _source(f"frontend/js/modules/{name}")
        assert "syncTripPlanListEntry(" in source, (
            f"{name} saves a plan without refreshing its row in the list"
        )


def main() -> None:
    check_static_contract()
    check_itinerary_payload_carries_no_undeclared_field()
    check_free_stop_payload_carries_no_undeclared_field()
    check_agreed_visit_time_can_be_entered()
    check_planning_mode_is_saved_not_drafted()
    check_assets_are_stamped_with_the_build()
    check_calendar_dates_are_timezone_invariant()
    check_region_state_and_sibling_visit_draft_are_preserved()
    check_opening_visit_preparation_reveals_the_editor()
    check_editing_a_visit_keeps_the_readers_place()
    check_plan_header_survives_a_reload()
    check_applying_a_suggestion_keeps_the_airports()
    check_clearing_an_airport_clears_what_belonged_to_it()
    check_airport_transfer_fields_are_never_dead_controls()
    check_a_saved_airport_comes_back_after_a_reload()
    check_a_preview_keeps_choices_made_on_a_team_leg()
    check_the_plan_list_row_matches_the_saved_plan()
    print("PASS: Trip Planner frontend stability contracts")


if __name__ == "__main__":
    main()
