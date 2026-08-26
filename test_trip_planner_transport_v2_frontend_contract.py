"""Frontend contracts for the Batch 2 Trip Planner transport editor."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def _node(script: str) -> None:
    subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        env=os.environ.copy(),
        check=True,
        text=True,
    )


def check_static_contract() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    form = (MODULES / "trip-form.js").read_text(encoding="utf-8")
    draft = (MODULES / "trip-planning-draft.js").read_text(encoding="utf-8")
    actions = (MODULES / "trip-itinerary-actions.js").read_text(encoding="utf-8")
    transport_actions = (MODULES / "trip-transport-actions.js").read_text(encoding="utf-8")
    transport_view = (MODULES / "trip-transport-view.js").read_text(encoding="utf-8")
    itinerary_view = (MODULES / "trip-itinerary-view.js").read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")

    for element_id in (
        "trip-route-order-mode",
        "trip-transport-priority",
        "trip-departure-window-start",
        "trip-departure-window-end",
        "trip-return-window-start",
        "trip-return-window-end",
        "trip-leg-list",
        "trip-draft-status",
        "trip-origin-preset",
        "trip-destination-preset",
    ):
        assert f'id="{element_id}"' in index, element_id
    assert index.count('type="datetime-local"') >= 4
    assert "trip-planning-draft.js" in index
    assert "trip-transport-view.js" in index
    assert "trip-transport-actions.js" in index
    assert "trip-china-hubs.js" in index
    assert "trip-route-form.js" in index

    for field in (
        "route_order_mode",
        "transport_mode_priority",
        "departure_window_start",
        "departure_window_end",
        "return_window_start",
        "return_window_end",
        "stop_order",
        "stop_durations",
        "leg_overrides",
    ):
        assert field in draft or field in form, field
    assert "ApiClient.reorderTripStops" not in actions, "draft moves must not persist partial order"
    assert "route_order_mode: 'manual'" in actions
    assert "TripTransportActions.schedulePreview" in actions
    assert "manual_time_hours" in transport_actions and "manual_travel_half_days" in transport_actions
    assert "escapeHtml" in transport_view
    assert "State.tripBusy" in transport_actions
    assert "Save visit details" in itinerary_view
    assert "Stop duration (days)" in itinerary_view

    for english, chinese in (
        ("Allowed transport and priority", "允许的交通方式与优先级"),
        ("Automatic stop order", "自动规划拜访顺序"),
        ("Keep manual stop order", "保留人工拜访顺序"),
        ("Lock this leg", "锁定此交通段"),
        ("Draft changes are not saved.", "草稿更改尚未保存。"),
        ("Save visit details", "保存拜访信息"),
        ("Stop duration (days)", "停留时长（天）"),
    ):
        assert english in i18n and chinese in i18n


def check_china_hubs_and_manual_custom_state() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const listeners = new Map();
const elements = new Map();
const ids = [
  'trip-title', 'trip-start-date', 'trip-end-date', 'trip-plan-region',
  'trip-origin-name', 'trip-origin-lat', 'trip-origin-lng', 'trip-origin-preset',
  'trip-destination-name', 'trip-destination-lat', 'trip-destination-lng', 'trip-destination-preset',
  'trip-avoid-weekends', 'trip-holidays', 'trip-description',
];
ids.forEach(id => elements.set(id, {
  value: id.endsWith('-preset') ? 'custom' : '',
  addEventListener(event, callback) { listeners.set(`${id}:${event}`, callback); },
}));
let scheduled = 0;
let writeCalls = 0;
const context = {
  console,
  State: {
    tripBusy: false,
    currentTripPlan: { id: 'p1', stops: [{ id: 'a' }], legs: [] },
  },
  document: {
    readyState: 'complete',
    getElementById: id => elements.get(id) || null,
  },
  I18n: { t: value => value },
  toDateInput: () => '2026-09-15',
  formatDate: value => value,
  TripTransportView: { render() {} },
  ApiClient: new Proxy({}, { get() { return () => { writeCalls += 1; }; } }),
  alert(message) { throw new Error(message); },
  notify() {},
  setTimeout() { scheduled += 1; return scheduled; },
  clearTimeout() {},
};
context.window = context;
vm.createContext(context);
for (const file of [
  'frontend/js/modules/trip-duration.js',
  'frontend/js/modules/trip-form.js',
  'frontend/js/modules/trip-stop-duration-payload.js',
  'frontend/js/modules/trip-planning-draft.js',
  'frontend/js/modules/trip-china-hubs.js',
  'frontend/js/modules/trip-transport-actions.js',
  'frontend/js/modules/trip-route-form.js',
]) vm.runInContext(fs.readFileSync(file, 'utf8'), context);
context.TripPlanningDraft.hydrate(context.State.currentTripPlan);

const hubs = {
  PVG: ['Shanghai Pudong International Airport (PVG)', 31.1443, 121.8083],
  PEK: ['Beijing Capital International Airport (PEK)', 40.0799, 116.6031],
  CAN: ['Guangzhou Baiyun International Airport (CAN)', 23.3924, 113.2988],
  SZX: ["Shenzhen Bao'an International Airport (SZX)", 22.6393, 113.8107],
};
for (const [code, expected] of Object.entries(hubs)) {
  context.TripTransportActions.hubChanged('origin', code);
  assert.strictEqual(elements.get('trip-origin-name').value, expected[0]);
  assert.strictEqual(elements.get('trip-origin-lat').value, expected[1]);
  assert.strictEqual(elements.get('trip-origin-lng').value, expected[2]);
}
context.TripTransportActions.hubChanged('destination', 'PVG');
assert.strictEqual(elements.get('trip-destination-name').value, hubs.PVG[0]);
assert.strictEqual(context.TripPlanningDraft.get().dirty, true);
assert(scheduled >= 5, 'hub changes should schedule read-only previews');
assert.strictEqual(writeCalls, 0, 'hub changes must not call a write API');

elements.get('trip-origin-preset').value = 'PVG';
elements.get('trip-origin-name').value = 'Custom Shanghai office';
listeners.get('trip-origin-name:change')();
assert.strictEqual(elements.get('trip-origin-preset').value, 'custom');
assert.strictEqual(elements.get('trip-origin-name').value, 'Custom Shanghai office');
"""
    _node(script)


def check_only_other_validation_gate() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = {
  console,
  State: { currentTripPlan: { legs: [{ leg_key: 'origin>a' }, { leg_key: 'a>destination' }] } },
  document: { readyState: 'complete', getElementById() { return null; } },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-route-form.js', 'utf8'), context);
const key = 'When Other is the only transport mode, keep an estimated mode for the first preview, then set Other with manual hours or days on every leg.';
const base = { transport_mode_priority: ['other'], stop_order: [], leg_overrides: {} };
assert.strictEqual(context.TripRouteForm.validationError(base), key);
assert.strictEqual(context.TripRouteForm.validationError({ ...base, leg_overrides: {
  'origin>a': { selected_mode: 'other', manual_time_hours: 2 },
} }), key);
assert.strictEqual(context.TripRouteForm.validationError({ ...base, leg_overrides: {
  'origin>a': { selected_mode: 'other', manual_time_hours: 2 },
  'a>destination': { selected_mode: 'other', manual_travel_half_days: 2 },
} }), null);
"""
    _node(script)


def check_route_header_draft_survives_same_plan_refresh() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const elements = new Map();
function field(id, value = '', checked = false) {
  const element = { id, value, checked };
  elements.set(id, element);
  return element;
}
[
  'trip-title', 'trip-start-date', 'trip-end-date', 'trip-plan-region',
  'trip-origin-name', 'trip-origin-lat', 'trip-origin-lng', 'trip-origin-preset',
  'trip-destination-name', 'trip-destination-lat', 'trip-destination-lng', 'trip-destination-preset',
  'trip-route-order-mode', 'trip-travel-mode', 'trip-departure-window-start',
  'trip-departure-window-end', 'trip-return-window-start', 'trip-return-window-end',
  'trip-holidays', 'trip-description', 'stop-stay-a',
].forEach(id => field(id));
field('trip-avoid-weekends', '', true);
const base = {
  id: 'p1', title: 'DB old title', start_date: '2026-09-01', end_date: '2026-09-10',
  region: 'EU', origin_name: 'DB old origin', origin_lat: 1, origin_lng: 2,
  destination_name: 'DB old return', destination_lat: 3, destination_lng: 4,
  avoid_weekends: true, holiday_dates: [], description: 'DB old notes',
  route_order_mode: 'manual', transport_mode_priority: ['flight', 'drive'],
  stops: [{ id: 'a', stay_days: 1 }],
  legs: [{ leg_key: 'origin>a', selected_mode: 'flight' }, { leg_key: 'a>destination', selected_mode: 'flight' }],
};
const context = {
  console,
  Date,
  State: { tripBusy: false, tripCandidatePagination: { limit: 25, offset: 0 }, currentTripPlan: base },
  document: { readyState: 'complete', getElementById: id => elements.get(id) || null },
  TripTransportView: { render() {} },
  I18n: { t: value => value },
  toDateInput: () => '2026-09-15',
  formatDate: value => value,
  alert(message) { throw new Error(message); }, notify() {},
  setTimeout() { return 1; }, clearTimeout() {},
};
context.window = context;
vm.createContext(context);
for (const file of [
  'frontend/js/modules/trip-duration.js',
  'frontend/js/modules/trip-form.js',
  'frontend/js/modules/trip-stop-duration-payload.js',
  'frontend/js/modules/trip-planning-draft.js',
  'frontend/js/modules/trip-china-hubs.js',
  'frontend/js/modules/trip-transport-actions.js',
]) vm.runInContext(fs.readFileSync(file, 'utf8'), context);
context.populateTripPlanForm(base, { committed: true });

context.TripTransportActions.hubChanged('origin', 'PVG');
elements.get('trip-title').value = 'September customer tour';
elements.get('trip-start-date').value = '2026-09-15';
elements.get('trip-end-date').value = '2026-09-30';
elements.get('trip-plan-region').value = 'EU';
elements.get('trip-destination-name').value = 'Shenzhen office';
elements.get('trip-destination-lat').value = '22.5431';
elements.get('trip-destination-lng').value = '114.0579';
elements.get('trip-avoid-weekends').checked = false;
elements.get('trip-holidays').value = '2026-09-18, 2026-09-25';
elements.get('trip-description').value = 'Keep this unsaved note';
elements.get('trip-departure-window-start').value = '2026-09-14T18:00';
elements.get('trip-departure-window-end').value = '2026-09-15T12:00';
elements.get('trip-return-window-start').value = '2026-09-29T18:00';
elements.get('trip-return-window-end').value = '2026-09-30T23:00';
context.TripTransportActions.routeFieldChanged();
context.TripTransportActions.headerChanged();
context.TripPlanningDraft.change(draft => {
  draft.routeOrderMode = 'manual';
  draft.stopDurations.a = { half_days: 3, preferred_period: 'auto', locked: false };
  draft.legOverrides['origin>a'] = {
    selected_mode: 'drive', mode_locked: true,
    manual_distance_km: null, manual_time_hours: null,
    manual_travel_half_days: null, notes: 'Keep this lock',
  };
});

const addedRefresh = {
  ...base,
  stops: [{ id: 'a', stay_days: 1 }, { id: 'b', stay_days: 1 }],
  legs: [
    { leg_key: 'origin>a', selected_mode: 'flight' },
    { leg_key: 'a>b', selected_mode: 'drive' },
    { leg_key: 'b>destination', selected_mode: 'flight' },
  ],
};
context.State.currentTripPlan = addedRefresh;
context.populateTripPlanForm(addedRefresh);
const removedRefresh = { ...base };
context.State.currentTripPlan = removedRefresh;
context.populateTripPlanForm(removedRefresh);

assert.strictEqual(elements.get('trip-title').value, 'September customer tour');
assert.strictEqual(elements.get('trip-start-date').value, '2026-09-15');
assert.strictEqual(elements.get('trip-end-date').value, '2026-09-30');
assert.strictEqual(elements.get('trip-origin-preset').value, 'PVG');
assert.strictEqual(elements.get('trip-origin-name').value, 'Shanghai Pudong International Airport (PVG)');
assert.strictEqual(elements.get('trip-avoid-weekends').checked, false);
assert.strictEqual(elements.get('trip-holidays').value, '2026-09-18, 2026-09-25');
assert.strictEqual(elements.get('trip-description').value, 'Keep this unsaved note');
assert.strictEqual(elements.get('trip-departure-window-start').value, '2026-09-14T18:00');
assert.strictEqual(elements.get('trip-return-window-end').value, '2026-09-30T23:00');

// The real stop card is rendered from the durable draft after each refresh.
// Mirror that visible 1.5-day field in this DOM-only harness.
elements.get('stop-stay-a').value = '1.5';
const payload = context.readTripItineraryPayload();
assert.strictEqual(payload.title, 'September customer tour');
assert.strictEqual(payload.start_date, '2026-09-15');
assert.strictEqual(payload.end_date, '2026-09-30');
assert.strictEqual(payload.origin_lat, 31.1443);
assert.strictEqual(payload.origin_lng, 121.8083);
assert.strictEqual(payload.destination_name, 'Shenzhen office');
assert.strictEqual(payload.avoid_weekends, false);
assert.deepStrictEqual(Array.from(payload.holiday_dates), ['2026-09-18', '2026-09-25']);
assert.strictEqual(payload.departure_window_start, '2026-09-14T18:00');
assert.strictEqual(payload.return_window_end, '2026-09-30T23:00');
assert.deepStrictEqual(Array.from(payload.stop_order), ['a']);
assert.strictEqual(payload.stop_durations.a.half_days, 3);
assert.strictEqual(Object.hasOwn(payload, 'stop_stays'), false);
assert.strictEqual(payload.leg_overrides['origin>a'].mode_locked, true);

context.TripTransportActions.routeModeChanged('auto');
const autoPayload = context.readTripItineraryPayload();
assert.strictEqual(autoPayload.route_order_mode, 'auto');
assert.strictEqual(autoPayload.stop_order, null);
assert.deepStrictEqual(Object.keys(autoPayload.leg_overrides), []);

const planB = {
  ...base, id: 'p2', title: 'Plan B', region: 'SEA', origin_name: 'Guangzhou',
  origin_lat: 23.1, origin_lng: 113.2, holiday_dates: ['2026-10-01'],
};
context.State.currentTripPlan = planB;
context.populateTripPlanForm(planB, { committed: true });
assert.strictEqual(context.TripPlanningDraft.get().planId, 'p2');
assert.strictEqual(elements.get('trip-title').value, 'Plan B');
assert.strictEqual(elements.get('trip-start-date').value, '2026-09-01');
assert.strictEqual(elements.get('trip-origin-preset').value, 'custom');
assert.strictEqual(context.readTripItineraryPayload().description, 'DB old notes');
"""
    _node(script)


def check_draft_payload_and_commit_lifecycle() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const context = {
  console,
  State: { currentTripPlan: null },
  TripTransportView: { render() {} },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-planning-draft.js', 'utf8'), context);

const plan = {
  id: 'p1', travel_mode: 'auto', stops: [
    { id: 'a', stay_days: 1 }, { id: 'b', stay_days: 2 },
  ], legs: [],
};
let state = context.TripPlanningDraft.hydrate(plan);
assert.deepStrictEqual(Array.from(state.transportModePriority), ['flight', 'drive', 'ground_public']);
assert.deepStrictEqual(Array.from(state.stopOrder), ['a', 'b']);
assert.strictEqual(context.TripPlanningDraft.itineraryPayload().stop_order, null);
const cleanRevision = context.TripPlanningDraft.revision();
assert.strictEqual(context.TripPlanningDraft.previewApplied(plan, cleanRevision), true);
assert.strictEqual(context.TripPlanningDraft.get().dirty, true);
context.TripPlanningDraft.hydrate(plan, { committed: true });
assert.strictEqual(context.TripPlanningDraft.get().dirty, false);
context.TripPlanningDraft.change(draft => {
  draft.routeOrderMode = 'manual';
  draft.transportModePriority = ['ground_public', 'flight'];
  draft.departureWindowStart = '2026-09-14T18:00';
  draft.departureWindowEnd = '2026-09-15T12:00';
  draft.returnWindowStart = '2026-09-29T18:00';
  draft.returnWindowEnd = '2026-09-30T23:00';
  draft.stopOrder = ['b', 'a'];
  draft.stopDurations.a = { half_days: 3, preferred_period: 'auto', locked: false };
  draft.legOverrides['b>a'] = {
    selected_mode: 'other', mode_locked: true,
    manual_distance_km: 50, manual_time_hours: 2.5,
    manual_travel_half_days: 2, notes: 'Private transfer',
  };
});
const payload = context.TripPlanningDraft.itineraryPayload();
assert.strictEqual(payload.route_order_mode, 'manual');
assert.deepStrictEqual(Array.from(payload.transport_mode_priority), ['ground_public', 'flight']);
assert.deepStrictEqual(Array.from(payload.stop_order), ['b', 'a']);
assert.strictEqual(payload.stop_durations.a.half_days, 3);
assert.strictEqual(Object.hasOwn(payload, 'stop_stays'), false);
assert.strictEqual(payload.leg_overrides['b>a'].selected_mode, 'other');
assert.strictEqual(payload.leg_overrides['b>a'].manual_time_hours, 2.5);
assert.strictEqual(payload.departure_window_start, '2026-09-14T18:00');
assert.strictEqual(payload.return_window_end, '2026-09-30T23:00');
assert.strictEqual(context.TripPlanningDraft.get().dirty, true);

const preview = {
  ...plan, route_order_mode: 'manual',
  transport_mode_priority: ['ground_public', 'flight'],
  stops: [{ id: 'b', stay_days: 2 }, { id: 'a', stay_days: 3 }],
  legs: [{
    leg_key: 'b>a', selected_mode: 'other', mode_locked: true,
    manual_distance_km: 50, manual_time_hours: 2.5,
    manual_travel_half_days: 2, notes: 'Private transfer',
  }],
};
const revision = context.TripPlanningDraft.revision();
assert.strictEqual(context.TripPlanningDraft.previewApplied(preview, revision), true);
assert.strictEqual(context.TripPlanningDraft.get().dirty, true);
assert.strictEqual(context.TripPlanningDraft.get().previewReady, true);
context.TripPlanningDraft.hydrate(preview, { committed: true });
assert.strictEqual(context.TripPlanningDraft.get().dirty, false);
assert.strictEqual(context.TripPlanningDraft.get().legOverrides['b>a'].manual_time_hours, 2.5);
"""
    _node(script)


def check_removed_stop_prunes_invalid_leg_overrides() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = { console, State: { currentTripPlan: null }, TripTransportView: { render() {} } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-planning-draft.js', 'utf8'), context);
const locked = leg_key => ({ leg_key, selected_mode: 'drive', mode_locked: true });
const original = {
  id: 'p-legs', route_order_mode: 'manual',
  stops: [{ id: 'a' }, { id: 'b' }, { id: 'c' }],
  legs: ['origin>a', 'a>b', 'b>c', 'c>destination'].map(locked),
};
context.TripPlanningDraft.hydrate(original);
context.TripPlanningDraft.change(() => {});
const afterRemoval = {
  ...original,
  stops: [{ id: 'a' }, { id: 'c' }],
  // Simulate a stale server summary that still contains the removed stop.
  legs: original.legs,
};
context.TripPlanningDraft.hydrate(afterRemoval);
const payload = context.TripPlanningDraft.itineraryPayload();
assert.deepStrictEqual(Array.from(payload.stop_order), ['a', 'c']);
assert.deepStrictEqual(Object.keys(payload.leg_overrides).sort(), ['c>destination', 'origin>a']);
assert.strictEqual(Object.hasOwn(payload.leg_overrides, 'a>b'), false);
assert.strictEqual(Object.hasOwn(payload.leg_overrides, 'b>c'), false);
"""
    _node(script)


def check_manual_move_and_generate_payload() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

let captured = null;
let previewScheduled = 0;
const elements = new Map([['trip-route-order-mode', { value: 'auto' }]]);
const committed = {
  id: 'p1', row_version: 8, route_order_mode: 'manual',
  transport_mode_priority: ['flight', 'drive'],
  stops: [{ id: 'b', sequence_no: 1 }, { id: 'a', sequence_no: 2 }], legs: [],
};
const context = {
  console,
  State: {
    tripBusy: false,
    tripCandidatePagination: { offset: 0 },
    currentTripPlan: {
      id: 'p1', row_version: 7, travel_mode: 'auto', legs: [],
      stops: [{ id: 'a', sequence_no: 1, stay_days: 1 }, { id: 'b', sequence_no: 2, stay_days: 1 }],
    },
  },
  document: { getElementById: id => elements.get(id) || null },
  I18n: { t: value => value },
  TripTransportView: { render() {} },
  TripTransportActions: { schedulePreview() { previewScheduled += 1; } },
  ApiClient: {
    async generateTripItinerary(planId, payload) {
      assert.strictEqual(planId, 'p1');
      captured = payload;
      return committed;
    },
  },
  notify() {}, alert(message) { throw new Error(message); }, confirm() { return true; },
  setInputValue(id, value) { const el = elements.get(id); if (el) el.value = value; },
  setTripBusy(value) { context.State.tripBusy = value; },
  renderCurrentTripPlan() {}, renderTripMap() {}, renderTripPlans() {},
  populateTripPlanForm(plan, options) { context.TripPlanningDraft.hydrate(plan, options); },
  readTripItineraryPayload() { return context.TripPlanningDraft.itineraryPayload(); },
  async handleTripError(error) { throw error; },
  downloadBlob() {}, loadTripPlanner: async () => {},
  TripPlannerModule: { renderVisitExecution() {} },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-planning-draft.js', 'utf8'), context);
context.TripPlanningDraft.hydrate(context.State.currentTripPlan);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-itinerary-actions.js', 'utf8'), context);

(async () => {
  await context.moveTripStop('a', 1);
  assert.deepStrictEqual(context.State.currentTripPlan.stops.map(item => item.id), ['b', 'a']);
  assert.strictEqual(context.State.currentTripPlan.route_order_mode, 'manual');
  assert.strictEqual(context.TripPlanningDraft.get().routeOrderMode, 'manual');
  assert.deepStrictEqual(Array.from(context.TripPlanningDraft.get().stopOrder), ['b', 'a']);
  assert.strictEqual(elements.get('trip-route-order-mode').value, 'manual');
  assert.strictEqual(previewScheduled, 1);
  await context.generateCurrentTripItinerary();
  assert(captured, 'generate payload was not sent');
  assert.strictEqual(captured.row_version, 7);
  assert.strictEqual(captured.route_order_mode, 'manual');
  assert.deepStrictEqual(Array.from(captured.stop_order), ['b', 'a']);
  assert.strictEqual(context.TripPlanningDraft.get().dirty, false);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    _node(script)


def check_transport_rendering_escapes_leg_content() -> None:
    script = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const roots = {
  'trip-transport-priority': { innerHTML: '' },
  'trip-leg-list': { innerHTML: '' },
  'trip-leg-count': { textContent: '' },
  'trip-draft-status': { className: '', textContent: '' },
};
const escapeHtml = value => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
const context = {
  console, escapeHtml,
  document: { getElementById: id => roots[id] || null },
  I18n: { t: (value, params = {}) => String(value).replace('{count}', params.count ?? '') },
  TripPlanningDraft: { MODES: ['flight', 'drive', 'ground_public', 'other'] },
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-duration.js', 'utf8'), context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-transport-view.js', 'utf8'), context);
context.TripTransportView.render({ legs: [{
  leg_key: 'x"><img src=x onerror=1>', from_label: '<script>from</script>',
  to_label: '<img src=x>', selected_mode: 'drive', distance_km: 1,
  time_hours: 1, travel_half_days: 2,
}] }, {
  transportModePriority: ['drive'], legOverrides: {}, dirty: true, previewReady: true,
});
const html = roots['trip-leg-list'].innerHTML;
assert.strictEqual(html.includes('<script>'), false);
assert.strictEqual(html.includes('<img src=x>'), false);
assert.strictEqual(html.includes('&lt;script&gt;'), true);
assert.strictEqual(html.includes('&lt;img src=x&gt;'), true);
"""
    _node(script)


def run() -> None:
    check_static_contract()
    check_china_hubs_and_manual_custom_state()
    check_only_other_validation_gate()
    check_route_header_draft_survives_same_plan_refresh()
    check_draft_payload_and_commit_lifecycle()
    check_removed_stop_prunes_invalid_leg_overrides()
    check_manual_move_and_generate_payload()
    check_transport_rendering_escapes_leg_content()
    print("PASS: Trip Planner transport v2 frontend contracts")


if __name__ == "__main__":
    run()
