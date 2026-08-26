"""Runtime contracts for Trip Planner date, draft, and region isolation.

Run:
    python test_trip_planner_stability_frontend_contract.py

The Node harness uses no browser or network access.  It executes the shipped
frontend modules in isolated VM contexts and repeats date checks under widely
separated time zones.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


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


def main() -> None:
    check_static_contract()
    check_calendar_dates_are_timezone_invariant()
    check_region_state_and_sibling_visit_draft_are_preserved()
    print("PASS: Trip Planner frontend stability contracts")


if __name__ == "__main__":
    main()
