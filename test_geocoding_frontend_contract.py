#!/usr/bin/env python3
"""Browser-side contracts for candidates, postal codes and bounded list rendering."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def test_static_contracts() -> None:
    api = (ROOT / "frontend/js/api-client.js").read_text(encoding="utf-8")
    actions = (ROOT / "frontend/js/modules/coordinate-actions.js").read_text(encoding="utf-8")
    batch = (ROOT / "frontend/js/modules/batch-geocode.js").read_text(encoding="utf-8")
    batch_data = (ROOT / "frontend/js/modules/batch-geocode-data.js").read_text(encoding="utf-8")
    review = (ROOT / "frontend/js/modules/coordinate-review-view.js").read_text(encoding="utf-8")
    review_table = (ROOT / "frontend/js/modules/coordinate-review-table.js").read_text(encoding="utf-8")
    assert "/intake/geocode/search" in api and "searchGeocode" in api
    assert "postal_code" in actions and "err?.details?.code" in actions
    assert "customer.row_version" in batch
    assert "geocode_confidence: 'medium'" in batch
    assert "geocode_locked: false" in batch
    assert "BatchGeocodeData.snapshot" in batch and "item.can_edit === true" in batch_data
    assert "COORDINATE_REVIEW_PAGE_SIZE" in review and "items.map(row)" in review_table
    assert len(batch.splitlines()) <= 125 and len(review.splitlines()) <= 125


def test_browser_contracts() -> None:
    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const elements = new Map();
function element(extra = {}) {
  return Object.assign({ value: '', textContent: '', className: '', innerHTML: '',
    hidden: false, style: {}, dataset: {}, disabled: false, scrollIntoView() {} }, extra);
}
for (const [id, value] of Object.entries({
  'coord-address': 'Arc de Triomphe', 'coord-city': 'Paris',
  'coord-postal-code': '75008', 'coord-country': 'France',
  'coord-lat': '', 'coord-lng': '',
})) elements.set(id, element({ value }));
elements.set('coord-geocode-btn', element({ textContent: 'Find on map' }));
elements.set('coord-geocode-result', element());
elements.set('coord-geocode-candidates', element());
elements.set('coordinate-review-list', element());

let submitted = null;
const context = {
  console,
  setTimeout: fn => { fn(); return 1; }, clearTimeout() {},
  document: {
    getElementById: id => elements.get(id) || null,
    querySelector: () => null,
    querySelectorAll: () => [],
  },
  alert() {}, notify() {}, hideModal() {},
  escapeHtml: value => String(value ?? ''),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text) },
  ApiClient: {
    searchGeocode: async fields => {
      submitted = fields;
      return { candidates: [
        { lat: 48.8737917, lng: 2.2950275, normalized_address: '75008 Paris', confidence: 'high' },
        { lat: 48.87, lng: 2.30, normalized_address: 'Paris', confidence: 'low' },
      ] };
    },
  },
  State: { mapData: null },
};
context.window = context;
vm.createContext(context);
for (const path of [
  'frontend/js/modules/batch-geocode-data.js',
  'frontend/js/modules/coordinate-state.js',
  'frontend/js/modules/coordinate-fields.js',
  'frontend/js/modules/coordinate-geocode-view.js',
  'frontend/js/modules/coordinate-busy-view.js',
  'frontend/js/modules/coordinate-actions.js',
  'frontend/js/modules/coordinate-review-data.js',
  'frontend/js/modules/coordinate-review-table.js',
  'frontend/js/modules/coordinate-review-view.js',
  'frontend/js/modules/coordinate-review-actions.js',
]) vm.runInContext(fs.readFileSync(path, 'utf8'), context, { filename: path });
context.updateCoordinateMarker = () => {};

(async () => {
  await context.geocodeCoordinateAddress();
  assert.strictEqual(submitted.postal_code, '75008');
  assert.strictEqual(elements.get('coord-lat').value, '48.873792');
  assert.ok(elements.get('coord-geocode-candidates').innerHTML.includes('75008 Paris'));
  assert.ok(elements.get('coord-geocode-result').textContent.includes('Found 2 matches'));

  const points = Array.from({ length: 85 }, (_, index) => ({
    customer_id: `c-${index}`, customer_name: `Customer ${index}`,
    lat: 48 + index / 1000, lng: 2, lead_count: 85 - index,
    coordinate_quality: 'exact', geocode_locked: true, can_edit: true,
  }));
  vm.runInContext(`coordinateReviewData = ${JSON.stringify({ points, missing_locations: [] })}; renderCoordinateReviewList();`, context);
  let html = elements.get('coordinate-review-list').innerHTML;
  assert.strictEqual((html.match(/openCoordinateCorrectionFromReview/g) || []).length, 40);
  assert.ok(html.includes('Showing 1–40 of 85'));
  context.changeCoordinateReviewPage(1);
  html = elements.get('coordinate-review-list').innerHTML;
  assert.ok(html.includes('Showing 41–80 of 85'));

  const batch = context.BatchGeocodeData.snapshot({
    points: [
      { customer_id: 'editable', needs_geocode: true, can_edit: true },
      { customer_id: 'readonly', needs_geocode: true, can_edit: false },
    ],
    missing_locations: [{ customer_id: 'missing', can_edit: true }],
  });
  assert.strictEqual(batch.total, 2);
  assert.strictEqual(JSON.stringify(batch.customers.map(item => item.id)), '["editable","missing"]');
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        ["node", "-e", harness], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr or result.stdout


def main() -> None:
    test_static_contracts()
    print("PASS: test_static_contracts")
    test_browser_contracts()
    print("PASS: test_browser_contracts")
    print("PASS: geocoding frontend regression completed")


if __name__ == "__main__":
    main()
