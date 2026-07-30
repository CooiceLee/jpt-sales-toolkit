"""Runtime contracts for deterministic business sorting across card worklists."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"


def main() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    sort_source = (MODULES / "worklist-sort.js").read_text(encoding="utf-8")
    sales = (MODULES / "sales-worklists.js").read_text(encoding="utf-8")
    sampling = (MODULES / "sampling.js").read_text(encoding="utf-8")
    service = (MODULES / "service-worklists.js").read_text(encoding="utf-8")
    repository = (
        ROOT / "backend" / "repositories" / "lead_repository.py"
    ).read_text(encoding="utf-8")

    assert index.index("worklist-sort.js") < index.index("sales-worklists.js")
    assert index.index("worklist-sort.js") < index.index("sampling.js")
    assert index.index("worklist-sort.js") < index.index("service-worklists.js")
    for call in ("handler", "followup", "deal"):
        assert f"WorklistSort.{call}" in sales
    assert "WorklistSort.sampling" in sampling
    assert "WorklistSort.fulfillment" in service
    assert "WorklistSort.aftersales" in service
    assert "_afterSalesTasks: leadTasks" in service
    assert "sample_task_updated_at:" in sampling
    assert len(sort_source.splitlines()) <= 125
    stable_order = (
        "ORDER BY l.updated_at DESC, l.display_id ASC, l.id ASC LIMIT ? OFFSET ?"
    )
    assert repository.count(stable_order) == 2

    harness = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const context = { console, Date, Math, Set };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(
  'frontend/js/modules/worklist-sort.js', 'utf8'
), context);
const sort = context.WorklistSort;
const ids = values => Array.from(values, item => item.id);

const handler = [
  { id: 'h-b', inquiry_id: 'JPT-B', inquiry_date: '2026-01-01' },
  { id: 'h-a', inquiry_id: 'JPT-A', inquiry_date: '2026-01-01' },
  { id: 'h-c', inquiry_id: 'JPT-C', inquiry_date: '202506', created_at: '2025-12-01' },
  { id: 'h-d', inquiry_id: 'JPT-D', inquiry_date: '2026-02-30', created_at: 'bad' },
];
const snapshot = JSON.stringify(handler);
const handlerResult = sort.handler(handler);
assert.deepStrictEqual(ids(handlerResult), ['h-c', 'h-a', 'h-b', 'h-d']);
assert.strictEqual(JSON.stringify(handler), snapshot);
assert.notStrictEqual(handlerResult, handler);
assert.deepStrictEqual(ids(sort.handler([
  { id: 'tie-b', inquiry_id: 'JPT-TIE', inquiry_date: '2026-01-01' },
  { id: 'tie-a', inquiry_id: 'JPT-TIE', inquiry_date: '2026-01-01' },
])), ['tie-a', 'tie-b']);
assert.deepStrictEqual(ids(sort.handler([
  { id: 'tz-a', inquiry_id: 'JPT-A', inquiry_date: '2026-01-01T00:00:00' },
  { id: 'tz-b', inquiry_id: 'JPT-B', inquiry_date: '2026-01-01' },
])), ['tz-a', 'tz-b']);

const followup = [
  { id: 'f1', inquiry_id: 'F1', next_followup_date: '2026-07-10', activity_date: '2026-07-01' },
  { id: 'f2', inquiry_id: 'F2', next_followup_date: '2026-07-10', activity_date: '2026-06-01' },
  { id: 'f3', inquiry_id: 'F3', next_followup_date: '', activity_date: '2026-05-01' },
  { id: 'f4', inquiry_id: 'F4', next_followup_date: '202507', activity_date: '2026-04-01' },
];
assert.deepStrictEqual(ids(sort.followup(followup)), ['f2', 'f1', 'f4', 'f3']);
assert.deepStrictEqual(
  ids(sort.followup(followup, { activityMode: '30' })),
  ['f4', 'f3', 'f2', 'f1']
);

const sampling = [
  { id: 's1', inquiry_id: 'S1', sample_status: 'In Progress', sample_due_date: '2026-07-02' },
  { id: 's2', inquiry_id: 'S2', sample_status: 'Open', sample_due_date: '2026-07-01' },
  { id: 's3', inquiry_id: 'S3', sample_status: 'Completed', sample_task_updated_at: '2026-07-20' },
  { id: 's4', inquiry_id: 'S4', sample_status: 'Cancelled', sample_task_updated_at: '2026-07-10' },
  { id: 's5', inquiry_id: 'S5', sample_status: 'Open', sample_due_date: '' },
];
assert.deepStrictEqual(ids(sort.sampling(sampling)), ['s2', 's1', 's5', 's3', 's4']);

const deals = [
  { id: 'q-new', inquiry_id: 'Q2', stage: 'Quoted', quotation_date: '2026-07-02' },
  { id: 'q-old', inquiry_id: 'Q1', stage: 'Quoted', quotation_date: '2026-07-01' },
  { id: 'q-none', inquiry_id: 'Q3', stage: 'Quoted', quotation_date: '' },
  { id: 'l-old', inquiry_id: 'L1', stage: 'Lost', quotation_date: '2026-06-01' },
  { id: 'l-new', inquiry_id: 'L2', stage: 'Lost', quotation_date: '2026-06-02' },
];
assert.deepStrictEqual(
  ids(sort.deal(deals)), ['q-old', 'q-new', 'q-none', 'l-new', 'l-old']
);

const fulfillment = [
  { id: 'o-new', inquiry_id: 'O2', fulfillment_status: 'In Progress', po_date: '2026-07-02' },
  { id: 'o-old', inquiry_id: 'O1', fulfillment_status: 'Not Started', po_date: '2026-07-01' },
  { id: 'o-none', inquiry_id: 'O3', fulfillment_status: 'In Progress', po_date: '' },
  { id: 'c-old', inquiry_id: 'C1', fulfillment_status: 'Completed', po_date: '2026-06-01' },
  { id: 'c-new', inquiry_id: 'C2', fulfillment_status: 'Completed', po_date: '2026-06-02' },
];
assert.deepStrictEqual(
  ids(sort.fulfillment(fulfillment)),
  ['o-old', 'o-new', 'o-none', 'c-new', 'c-old']
);

const task = (status, due, created, updated) => ({
  status, due_date: due, created_at: created, updated_at: updated
});
const aftersales = [
  { id: 'a1', inquiry_id: 'A1', service_status: 'Open',
    _afterSalesTasks: [task('Open', '2026-07-02', '2026-06-02', '2026-07-02')] },
  { id: 'a2', inquiry_id: 'A2', service_status: 'In Progress',
    _afterSalesTasks: [task('In Progress', '2026-07-01', '2026-06-03', '2026-07-03')] },
  { id: 'a3', inquiry_id: 'A3', service_status: 'Open',
    _afterSalesTasks: [task('Open', '', '2026-06-01', '2026-07-01')] },
  { id: 'a4', inquiry_id: 'A4', service_status: 'Resolved',
    _afterSalesTasks: [task('Resolved', '', '2026-05-01', '2026-07-20')] },
  { id: 'a5', inquiry_id: 'A5', service_status: 'Closed',
    _afterSalesTasks: [task('Closed', '', '2026-05-02', '2026-07-10')] },
];
assert.deepStrictEqual(
  ids(sort.aftersales(aftersales)), ['a2', 'a1', 'a3', 'a4', 'a5']
);
"""
    result = subprocess.run(
        ["node", "-e", harness],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "TZ": "America/New_York"},
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: deterministic business sorting across all six card worklists")


if __name__ == "__main__":
    main()
