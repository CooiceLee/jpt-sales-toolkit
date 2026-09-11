"""The queues that share a shape share one implementation of it.

Three worklists now answer the same question - "which of these do I open
next?" - so the shell they use is one module: which view, how dense, where the
panel starts, what an empty list says. What each queue says in a row is its
own: the inquiry queue is decided on stage, date, product and amount; the
pre-sales queue on task status, due date, who is on it and how far it has got.
Copying one page's fields onto another is how a queue ends up showing columns
nobody there needs.

The amounts follow the rule the follow-up list already had to learn: the shared
card mapping answers 0 for "no deal amount", and read straight that printed
"Deal 0" over a lead nobody had priced.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
APP = (ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")
SHELL = (MODULES / "worklist-workbench.js").read_text(encoding="utf-8")
ROWS = (MODULES / "worklist-rows.js").read_text(encoding="utf-8")

QUEUES = ("handler", "sampling", "deal", "fulfillment", "aftersales")


def check_both_queues_have_the_whole_workbench() -> None:
    for key in QUEUES:
        for marker, why in (
            (f'id="{key}-state"', "no shared place for the empty or failed state"),
            (f'id="{key}-cards"', "the list has nowhere to render"),
            (f'id="{key}-table-body"', "the table view has no body"),
            (f'id="{key}-view-switch"', "there is no way to switch views"),
            (f'id="{key}-density-switch"', "there is no way to change density"),
            ('class="wb-layout"', "the two views are not in one frame"),
        ):
            assert marker in INDEX, f"{key}: {marker} - {why}"


def check_the_shell_is_written_once() -> None:
    """Three pages, one implementation of the shape."""
    for name in ("followup-workbench.js", "queue-workbenches.js"):
        module = (MODULES / name).read_text(encoding="utf-8")
        assert "WorklistWorkbench.create(" in module, (
            f"{name} does not use the shared shell"
        )
        for own in ("--wb-panel-top", "function setDensity", "function setView"):
            assert own not in module, (
                f"{name} keeps its own copy of {own}, so the pages will drift"
            )
    assert "--wb-panel-top" in SHELL and "getBoundingClientRect" in SHELL


def check_each_queue_keeps_its_own_columns() -> None:
    heads = ROWS[ROWS.index("const HEADS"):ROWS.index("function stageDot")]
    columns = {}
    for key in QUEUES:
        block = heads[heads.index(f"{key}:"):]
        columns[key] = block[:block.index("]")]
    assert "Task status" not in columns["handler"], "the inquiry queue shows sampling columns"
    assert "Inquiry date" not in columns["sampling"], "the pre-sales queue shows inquiry columns"
    assert "Quotation" in columns["deal"] and "Quotation" not in columns["fulfillment"]
    assert "Service status" in columns["aftersales"]
    # Five queues, five different sets: a page that copied another's columns
    # would show fields nobody there decides on.
    assert len({value for value in columns.values()}) == len(QUEUES), (
        f"two queues have identical columns: {columns}"
    )
    for key in QUEUES:
        block = INDEX[INDEX.index(f'id="module-{key}"'):]
        block = block[:block.index("</table>")]
        assert block.count("<th>") == 6, (
            f"{key}: the table head does not match the six fields the row spec has"
        )


def check_a_missing_amount_is_not_a_zero_deal() -> None:
    for name in ("handler-worklist.js", "sampling.js", "sales-worklists.js",
                 "service-worklists.js"):
        module = (MODULES / name).read_text(encoding="utf-8")
        for field in ("deal_amount", "estimated_value"):
            assert f"{field}: lead.{field} ?? null" in module, (
                f"{name} lets the card mapping flatten {field} to 0, so a lead "
                "nobody priced reads as an agreed amount of zero"
            )
    assert "MoneyTotals.text" in ROWS, "the row formats money itself"
    assert "'USD'" not in ROWS and '"USD"' not in ROWS, (
        "the row still has a dollar default to fall back on"
    )


def check_selection_and_escaping_are_the_production_ones() -> None:
    for marker, why in (
        ("data-inquiry-card", "the row is not selectable through the panel contract"),
        ("data-inquiry-id", "the row does not say which lead it is"),
        ('tabindex="0"', "the row cannot be reached by keyboard"),
        ("data-business", "business text is left for the translation walker"),
        ("escapeHtml", "customer names are written into the page unescaped"),
    ):
        assert marker in ROWS, f"{marker}: {why}"


def check_the_view_switch_is_not_a_filter() -> None:
    """The view and density buttons sit in the filter bar and share its look.

    Bound as filters, choosing "Table" on a list filtered to Quoted cleared the
    filter and brought every deal back, with no tab left marked active.
    """
    binder = (MODULES / "stage-filters.js").read_text(encoding="utf-8")
    assert "'.filter-tabs .filter-tab'" in binder, (
        "the filter binder still catches every tab-shaped button in the module, "
        "including the workbench's view and density switches"
    )
    assert "module.querySelectorAll('.filter-tab')" not in binder
    # And the switches really are outside the filter-tabs container.
    for key in QUEUES:
        block = INDEX[INDEX.index(f'id="module-{key}"'):]
        block = block[:block.index('class="wb-state"')]
        switch = block[block.index(f'id="{key}-view-switch"'):]
        assert "filter-tabs" not in switch[:switch.index("</div>")], (
            f"{key}: the view switch is inside the filter-tabs container"
        )


def check_the_panel_column_is_not_tied_to_one_page() -> None:
    assert "dataset.workbench" in APP, (
        "no page declares that it uses the list-beside-panel shape"
    )
    for key in ("followup", "handler", "sampling"):
        assert f"'{key}'" in APP[APP.index("dataset.workbench") - 400:
                                 APP.index("dataset.workbench") + 400], key
    assert ".app.detail-open[data-workbench] .detail-panel" in CSS, (
        "the panel only becomes a column on the page it was written for"
    )
    assert ".workbench-followup" not in CSS


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

const context = {
  console,
  escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.replaceAll(`{${key}}`, value), text),
    locale: () => 'en-US' },
  Intl,
};
context.window = context;
vm.createContext(context);
for (const file of ['money-totals-view.js', 'worklist-rows.js']) {
  vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`, 'utf8'), context);
}
const { row, tableRow, money } = context.WorklistRows;

// ---- what the amount says, with the real formatter --------------------
assert.equal(money({}), 'not quoted', 'nothing recorded should say so');
assert.ok(/EUR 0/.test(money({ deal_amount: 0, currency: 'EUR' })),
  'a deal agreed at zero reads as unpriced');
assert.ok(/Est\./.test(money({ estimated_value: 5000, currency: 'EUR' })),
  'an estimate is printed as an agreed amount');
assert.ok(!/USD/.test(money({ estimated_value: 10, currency: '' })),
  'a missing currency was filled in with dollars');

// ---- the row says what its own queue is decided on --------------------
const lead = {
  id: 'lead-1', inquiry_id: 'JPT-1', company_name: '<b>Bold</b> & Co',
  stage: 'New', inquiry_date: '2026-09-14', product_category: 'Laser',
  estimated_value: 42000, currency: 'EUR',
  sample_status: 'In Progress', sample_due_date: '2026-09-20',
  pre_sales_owner: 'Chen Wei', sample_progress: 'Sample cut',
};
const handler = row(lead, 'handler');
const sampling = row(lead, 'sampling');
assert.ok(handler.includes('&lt;b&gt;Bold&lt;/b&gt;'), 'the customer name is not escaped');
assert.ok(handler.includes('Laser') && !handler.includes('Sample cut'),
  'the inquiry row shows pre-sales fields');
assert.ok(sampling.includes('Sample cut') && !sampling.includes('Laser'),
  'the pre-sales row shows inquiry fields');
assert.ok(sampling.includes('Chen Wei') && sampling.includes('In Progress'));
assert.ok(handler.includes('data-inquiry-id="lead-1"'));
// The row is selectable the way the panel expects, in both views.
for (const type of ['handler', 'sampling']) {
  for (const markup of [row(lead, type), tableRow(lead, type)]) {
    assert.ok(/data-inquiry-card/.test(markup),
      `${type}: the row does not carry the selection contract`);
    assert.ok(/tabindex="0"/.test(markup), `${type}: the row is not focusable`);
    assert.ok(/data-inquiry-id="lead-1"/.test(markup), `${type}: no lead id`);
  }
}

// Both views say the same thing about the same lead.
for (const type of ['handler', 'sampling']) {
  const listed = row(lead, type);
  const tabled = tableRow(lead, type);
  const fields = type === 'handler' ? ['Laser', 'EUR'] : ['Chen Wei', 'In Progress'];
  fields.forEach(text => {
    assert.ok(listed.includes(text), `list ${type}: ${text}`);
    assert.ok(tabled.includes(text), `table ${type}: ${text}`);
  });
}

// A queue with nothing recorded still says something in every cell.
const bare = row({ id: 'bare' }, 'sampling');
assert.ok(!bare.includes('undefined') && !bare.includes('null'),
  'an empty field printed the word undefined');
console.log(JSON.stringify({ ok: true }));
"""


def check_the_rows_hold_up_on_real_tools() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"]


def main() -> None:
    check_both_queues_have_the_whole_workbench()
    check_the_shell_is_written_once()
    check_each_queue_keeps_its_own_columns()
    check_a_missing_amount_is_not_a_zero_deal()
    check_selection_and_escaping_are_the_production_ones()
    check_the_view_switch_is_not_a_filter()
    check_the_panel_column_is_not_tied_to_one_page()
    check_the_rows_hold_up_on_real_tools()
    print("PASS: the inquiry and pre-sales queues share the shape and keep "
          "their own fields")


if __name__ == "__main__":
    main()
