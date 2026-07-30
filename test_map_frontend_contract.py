#!/usr/bin/env python3
"""Runtime contracts for map coordinate safety and honest fallback rendering."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def main() -> None:
    index = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    app = (ROOT / "frontend/js/app.js").read_text(encoding="utf-8")
    trip_map = (ROOT / "frontend/js/modules/trip-candidates-map.js").read_text(
        encoding="utf-8"
    )
    map_support = (ROOT / "frontend/js/modules/map-support.js").read_text(
        encoding="utf-8"
    )
    coordinate_state = (ROOT / "frontend/js/modules/coordinate-state.js").read_text(
        encoding="utf-8"
    )
    coordinate_actions = (ROOT / "frontend/js/modules/coordinate-actions.js").read_text(
        encoding="utf-8"
    )
    coordinate_save = (ROOT / "frontend/js/modules/coordinate-save.js").read_text(
        encoding="utf-8"
    )
    lead_navigation = (ROOT / "frontend/js/modules/lead-navigation.js").read_text(
        encoding="utf-8"
    )
    batch_geocode = (ROOT / "frontend/js/modules/batch-geocode.js").read_text(
        encoding="utf-8"
    )
    style = (ROOT / "frontend/css/style.css").read_text(encoding="utf-8")

    ordered_scripts = [
        "map-support.js",
        "app.js",
        "review-map-view.js",
        "review-map.js",
        "trip-candidates-map.js",
    ]
    positions = [index.index(name) for name in ordered_scripts]
    assert positions == sorted(positions)
    assert "function initMap()" not in app
    assert "MapSupport.coordinatePair(candidate?.lat, candidate?.lng)" in trip_map
    assert "Number.isFinite(Number(candidate.lat))" not in trip_map
    assert "{count} customers · country aggregate" in (
        ROOT / "frontend/js/modules/review-map.js"
    ).read_text(encoding="utf-8")
    assert "confidenceKey" in (
        ROOT / "frontend/js/modules/review-map-view.js"
    ).read_text(encoding="utf-8")
    assert index.count('<option value="">All regions</option>') >= 3
    assert '<option value="">GLOBAL</option>' not in index
    assert "North America / Canada / Australia" in index
    assert "Russia / Turkey / Middle East" in index
    assert "Americas</option>" not in index and "Russia/India/ME" not in index
    assert "failedTiles === 0" in map_support
    assert "Object.freeze({" in coordinate_state
    assert "isCoordinateGeocodeRequestCurrent(request)" in coordinate_actions
    assert "request.customerId" in coordinate_save and "request.customerRowVersion" in coordinate_save
    assert "ApiClient.getCustomer" not in coordinate_save
    assert "ApiClient.updateCustomer(coordinateEditState.customerId" not in coordinate_save
    assert "postal_code: customer.postal_code" in lead_navigation
    assert "if (!mapRecord?.can_edit)" in lead_navigation
    assert "one or more configured external geocoding services" in index
    assert "one or more configured external geocoding services" in batch_geocode
    assert "coordinateEditState.geocodeProvider = result.provider || null" in coordinate_actions
    assert ".trip-layout {\n    grid-template-columns: 1fr;" in style
    _run_browser_contract()
    _run_coordinate_race_contract()
    print("PASS: map null safety, escaped labels, coordinate race safety and layout contracts")


def _run_browser_contract() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const elements = new Map([
  ['map-quality-filter', { value: '' }],
  ['map-summary', { innerHTML: '', textContent: '' }],
  ['world-map', {}],
]);
let markerPairs = [];
let fitBounds = [];
let focused = [];
let alerts = 0;
let tooltips = [];
let popups = [];
let mapLayerClears = 0;
function marker(pair) {
  assert.ok(Array.isArray(pair) && pair.length === 2);
  assert.ok(pair.every(Number.isFinite));
  markerPairs.push(pair);
  return {
    bindTooltip(value) { tooltips.push(value); return this; },
    bindPopup(value) { popups.push(value); return this; },
    addTo() { return this; },
    openPopup() { return this; },
    getLatLng() { return pair; },
  };
}
const context = {
  console,
  document: {
    getElementById: id => elements.get(id) || null,
    querySelector: () => null,
  },
  navigator: { onLine: true },
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text) },
  escapeHtml: value => String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
  formatMoney: value => String(value ?? 0),
  setText() {},
  alert: () => { alerts += 1; },
  switchModule() {},
  syncBatchGeocodeAccess() {},
  ApiClient: { getMapData: async () => { throw new Error('offline'); } },
  State: {
    map: {
      invalidateSize() {},
      fitBounds(bounds) { fitBounds = bounds; },
      setView() {},
    },
    mapLayer: { clearLayers() { mapLayerClears += 1; } },
    mapCustomerMarkers: {},
    tripMap: {
      fitBounds(bounds) { fitBounds = bounds; },
      setView(pair) { focused.push(pair); },
    },
    tripMapLayer: { clearLayers() {} },
    tripCandidates: [],
    currentTripPlan: null,
  },
  L: {
    circleMarker: marker,
    polyline: () => ({ addTo() { return this; } }),
  },
};
context.window = context;
vm.createContext(context);
for (const path of [
  'frontend/js/modules/map-support.js',
  'frontend/js/modules/review-map-view.js',
  'frontend/js/modules/review-map.js',
  'frontend/js/modules/trip-candidates-map.js',
]) {
  vm.runInContext(fs.readFileSync(path, 'utf8'), context, { filename: path });
}

assert.strictEqual(context.MapSupport.coordinatePair(null, null), null);
assert.strictEqual(context.MapSupport.coordinatePair('', ''), null);
assert.strictEqual(context.MapSupport.coordinatePair(91, 1), null);
assert.deepStrictEqual(
  Array.from(context.MapSupport.coordinatePair('0', '0')),
  [0, 0]
);

context.State.tripCandidates = [
  { customer_id: 'valid', customer_name: 'Valid', lat: '48.1', lng: '11.5', open_count: 1, score: 5 },
  { customer_id: 'missing', customer_name: 'Missing', lat: null, lng: null, open_count: 8, score: 9 },
  { customer_id: 'blank', customer_name: 'Blank', lat: '', lng: '', open_count: 3, score: 4 },
];
markerPairs = [];
context.renderTripMap();
assert.strictEqual(markerPairs.length, 1);
assert.deepStrictEqual(Array.from(markerPairs[0]), [48.1, 11.5]);
assert.strictEqual(fitBounds.length, 1);
context.focusTripCandidate(1);
assert.strictEqual(alerts, 1);
context.focusTripCandidate(0);
assert.deepStrictEqual(Array.from(focused[0]), [48.1, 11.5]);

context.State.currentTripPlan = {
  origin_lat: null, origin_lng: null,
  destination_lat: '', destination_lng: '',
  stops: [{ customer_id: 'missing', lat: null, lng: null }],
};
markerPairs = [];
context.renderTripMap();
assert.strictEqual(markerPairs.length, 1);

const mapData = {
  summary: { customers: 4, exact_points: 1, approximate_points: 2, missing_locations: 1 },
  missing_locations: [{ customer_id: 'none' }],
  points: [
    { customer_id: 'exact', customer_name: 'Exact', lat: 50, lng: 8, coordinate_quality: 'exact', lead_count: 1, leads: [] },
    { customer_id: 'fallback-1', customer_name: 'Fallback 1', country_code: 'DE', country_name: 'Germany', lat: 51.1, lng: 10.4, coordinate_quality: 'country_fallback', needs_geocode: true, lead_count: 2, leads: [] },
    { customer_id: 'fallback-2', customer_name: 'Fallback 2', country_code: 'DE', country_name: 'Germany', lat: 51.28, lng: 10.4, coordinate_quality: 'country_fallback', needs_geocode: true, lead_count: 3, leads: [] },
  ],
};
markerPairs = [];
context.renderReviewMap(mapData);
assert.strictEqual(markerPairs.length, 2, 'country fallbacks must render as one aggregate');
assert.strictEqual(context.State.mapCustomerMarkers['fallback-1'], context.State.mapCustomerMarkers['fallback-2']);
assert.ok(elements.get('map-summary').innerHTML.includes('2 visible markers'));

context.State.tripCandidates = [{
  customer_id: 'unsafe', customer_name: '<img src=x onerror=alert(1)>',
  city: '<script>bad()</script>', country: 'DE', lat: 48, lng: 9,
  open_count: '<img>', score: '<svg>', pipeline_value: 12,
}];
context.State.currentTripPlan = {
  origin_lat: 47, origin_lng: 8, origin_name: '<img src=x>',
  destination_lat: 49, destination_lng: 10, destination_name: '<svg onload=x>',
  stops: [{ customer_id: 'route-stop', lat: 48.5, lng: 9.5 }],
};
tooltips = [];
popups = [];
context.renderTripMap();
assert.ok(tooltips.length >= 3);
assert.ok(tooltips.every(value => !value.includes('<img') && !value.includes('<svg')));
assert.ok(popups.every(value => !value.includes('<script>') && !value.includes('<img src')));

tooltips = [];
context.renderReviewMap({
  summary: {}, missing_locations: [],
  points: [{ customer_id: 'unsafe-map', customer_name: '<img src=x>', lat: 1, lng: 2,
    coordinate_quality: 'exact', lead_count: 1, leads: [] }],
});
assert.ok(tooltips.every(value => !value.includes('<img')));

(async () => {
  context.State.mapData = { points: [{ customer_id: 'stale' }] };
  context.State.mapCustomerMarkers = { stale: {} };
  mapLayerClears = 0;
  await context.loadReviewMap();
  assert.strictEqual(mapLayerClears, 1);
  assert.strictEqual(context.State.mapData, null);
  assert.strictEqual(Object.keys(context.State.mapCustomerMarkers).length, 0);
  assert.strictEqual(elements.get('map-summary').textContent, 'Map data unavailable. Try again.');
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


def _run_coordinate_race_contract() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
};
const classes = () => {
  const values = new Set();
  return {
    add(name) { values.add(name); },
    remove(name) { values.delete(name); },
    contains(name) { return values.has(name); },
  };
};
const element = (value = '') => ({
  value, textContent: '', innerHTML: '', className: '', hidden: false, disabled: false,
  dataset: {}, style: {}, classList: classes(),
  closest() { return null; }, setAttribute() {},
});
const ids = new Map();
for (const id of [
  'coordinate-modal', 'coord-customer-name', 'coord-lat', 'coord-lng',
  'coord-address', 'coord-city', 'coord-postal-code', 'coord-country',
  'coord-geocode-btn', 'coord-geocode-result', 'coord-geocode-candidates',
  'coord-map-picker', 'module-coordinate-review', 'module-dashboard',
]) ids.set(id, element());
const saveButton = element();
const geocodeA = deferred();
const updateA = deferred();
const updates = [];
let notifications = 0;
let mapLoads = 0;
const context = {
  console,
  setTimeout() {},
  document: {
    getElementById: id => ids.get(id) || null,
    querySelector(selector) {
      if (selector === '#coordinate-modal .modal-footer .btn-primary') return saveButton;
      return null;
    },
    createElement: () => element(),
  },
  State: { config: { regions: { regions: {} } }, mapData: { points: [] } },
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text) },
  escapeHtml: value => String(value ?? ''),
  showModal(id) { ids.get(id).classList.add('show'); },
  hideModal(id) { ids.get(id).classList.remove('show'); },
  notify() { notifications += 1; },
  alert() {},
  loadReviewMap: async () => { mapLoads += 1; },
  loadCoordinateReview: async () => {},
  applyCoordinateReviewData() {},
  MapSupport: { coordinatePair: () => null },
  L: {},
  ApiClient: {
    searchGeocode: () => geocodeA.promise,
    getCustomer: async () => ({ row_version: 1 }),
    updateCustomer: (id, payload, rowVersion) => {
      updates.push({ id, payload, rowVersion });
      return id === 'A' ? updateA.promise : Promise.resolve({ id });
    },
  },
};
context.window = context;
vm.createContext(context);
for (const path of [
  'frontend/js/modules/coordinate-state.js',
  'frontend/js/modules/coordinate-fields.js',
  'frontend/js/modules/coordinate-geocode-view.js',
  'frontend/js/modules/coordinate-busy-view.js',
  'frontend/js/modules/coordinate-panel.js',
  'frontend/js/modules/coordinate-actions.js',
  'frontend/js/modules/coordinate-save.js',
]) vm.runInContext(fs.readFileSync(path, 'utf8'), context, { filename: path });

(async () => {
  context.openCoordinateCorrection('A', 'Customer A', null, null, {
    address: 'old address', city: 'Old City', country: 'DE',
  });
  const oldGeocode = context.geocodeCoordinateAddress();
  assert.strictEqual(ids.get('coord-geocode-btn').disabled, true);

  ids.get('coord-address').value = 'edited address';
  context.clearCoordinateGeocodeResult();
  assert.strictEqual(ids.get('coord-geocode-btn').disabled, false);
  context.openCoordinateCorrection('B', 'Customer B', null, null, {
    address: 'B address', city: 'B City', country: 'FR',
  });
  geocodeA.resolve({ candidates: [{ lat: 1, lng: 2, normalized_address: 'STALE A' }] });
  await oldGeocode;
  assert.strictEqual(ids.get('coord-customer-name').textContent, 'Customer B');
  assert.strictEqual(ids.get('coord-address').value, 'B address');
  assert.ok(!ids.get('coord-geocode-result').textContent.includes('STALE A'));
  assert.strictEqual(ids.get('coord-geocode-btn').disabled, false);

  context.openCoordinateCorrection('A', 'Customer A', 10, 20, {
    address: 'A save address', city: 'A City', country: 'DE', row_version: 7,
  });
  const saveA = context.saveCoordinates();
  assert.strictEqual(saveButton.disabled, true);
  context.openCoordinateCorrection('B', 'Customer B', 30, 40, {
    address: 'B remains visible', city: 'B City', country: 'FR', row_version: 8,
  });
  assert.strictEqual(saveButton.disabled, false);
  updateA.resolve({ id: 'A' });
  await saveA;
  assert.deepStrictEqual(updates.map(item => item.id), ['A']);
  assert.strictEqual(updates[0].payload.address, 'A save address');
  assert.strictEqual(updates[0].rowVersion, 7);
  assert.strictEqual(ids.get('coord-customer-name').textContent, 'Customer B');
  assert.strictEqual(ids.get('coord-address').value, 'B remains visible');
  assert.strictEqual(ids.get('coordinate-modal').classList.contains('show'), true);
  assert.strictEqual(saveButton.disabled, false);
  assert.strictEqual(notifications, 0);
  assert.strictEqual(mapLoads, 0);
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


if __name__ == "__main__":
    main()
