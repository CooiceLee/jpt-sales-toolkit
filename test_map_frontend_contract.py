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
    assert "All customer geographies" in index
    assert ".trip-layout {\n    grid-template-columns: 1fr;" in style
    _run_browser_contract()
    print("PASS: map null safety, fallback aggregation, network status and layout contracts")


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
function marker(pair) {
  assert.ok(Array.isArray(pair) && pair.length === 2);
  assert.ok(pair.every(Number.isFinite));
  markerPairs.push(pair);
  return {
    bindTooltip() { return this; },
    bindPopup() { return this; },
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
  escapeHtml: value => String(value ?? ''),
  formatMoney: value => String(value ?? 0),
  setText() {},
  alert: () => { alerts += 1; },
  switchModule() {},
  State: {
    map: {
      invalidateSize() {},
      fitBounds(bounds) { fitBounds = bounds; },
      setView() {},
    },
    mapLayer: { clearLayers() {} },
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
