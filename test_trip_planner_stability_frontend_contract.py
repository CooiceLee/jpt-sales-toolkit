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
    assert "TripExportActions.download(format)" in itinerary_actions
    assert "summary.stale === true || summary.valid === false" in export_actions
    assert "before exporting" in export_actions


def check_calendar_dates_are_timezone_invariant() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = {
    console,
    Date,
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
    sample: input('visit-sample-a', '', { checked: true }),
    quote: input('visit-quote-a', '', { checked: false }),
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
    State: {
        tripBusy: false,
        tripCandidatePagination: { limit: 25, offset: 0 },
        currentTripPlan: {
            id: 'plan-1', row_version: 7,
            stops: [{ id: 'a', row_version: 3 }, { id: 'b', row_version: 2 }],
        },
    },
    document: { getElementById: id => elements.get(id) || null },
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
  State: { currentTripPlan: { id: 'p1', stops: [] },
           tripCandidatePagination: { limit: 25, offset: 0 } },
  document: { getElementById: id => elements.get(id) || null },
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
  State: { currentTripPlan: { id: 'p1', stops: [] },
           tripCandidatePagination: { limit: 25, offset: 0 } },
  document: { getElementById: id => elements.get(id) || null },
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
  State: { currentTripPlan: { id: 'p1', route_order_mode: 'auto' } },
  document: { getElementById: id => nodes.get(id) || null },
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


def main() -> None:
    check_static_contract()
    check_itinerary_payload_carries_no_undeclared_field()
    check_agreed_visit_time_can_be_entered()
    check_planning_mode_is_saved_not_drafted()
    check_assets_are_stamped_with_the_build()
    check_calendar_dates_are_timezone_invariant()
    check_region_state_and_sibling_visit_draft_are_preserved()
    print("PASS: Trip Planner frontend stability contracts")


if __name__ == "__main__":
    main()
