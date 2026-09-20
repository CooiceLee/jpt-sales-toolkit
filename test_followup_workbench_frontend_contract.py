"""The follow-up list is a selector; the lead's own panel is the work surface.

A grid of equal cards gave every lead the same space and left the actual work -
reading one lead's history and writing the next step - in a panel squeezed
against the edge of the screen. The list now answers one question in a narrow
column and the panel takes the rest of the width.

What must not change while the shape does: the same items in the same order
from the same request, selection through the production [data-inquiry-card]
contract (so the panel, its drafts and its session identity are the real ones),
and every field a reader needs to recognise a lead - customer, progress, last
follow-up, next step, amount per currency.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
CSS = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
MODULE = INDEX[INDEX.index('id="module-followup"'):INDEX.index('id="module-sampling"')]


def check_the_empty_state_is_visible_in_both_views() -> None:
    """A filter that matches nothing has to say so wherever the reader is."""
    assert 'id="followup-state"' in MODULE, (
        "there is no shared place for the empty or failed state"
    )
    # The shell writes it, so that is where the rule lives now; the follow-up
    # module must hand it over rather than writing a second copy into the list.
    workbench = (ROOT / "frontend" / "js" / "modules" / "followup-workbench.js").read_text(
        encoding="utf-8")
    shell = (ROOT / "frontend" / "js" / "modules" / "worklist-workbench.js").read_text(
        encoding="utf-8")
    assert "drawEmpty(emptyCopy)" in workbench, (
        "the follow-up list draws its own empty state instead of the shared one"
    )
    empty = shell[shell.index("function drawEmpty"):shell.index("function draw(")]
    assert "state()" in empty and "box.hidden = false" in empty, (
        "the empty state is written into the list, which the table view hides"
    )
    assert "frame.hidden = true" in empty, (
        "both views stay on screen beside the empty state"
    )
    # One copy, placed once - not two texts to drift apart.
    assert shell.count("emptyState(") == 1 and workbench.count("emptyState(") == 0


def check_the_table_column_says_what_it_shows() -> None:
    header = MODULE[MODULE.index("<thead>"):MODULE.index("</thead>")]
    assert "Next step" not in header, (
        "a column headed 'next step' is filled with the last follow-up's note"
    )
    assert "Last follow-up note" in header
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    for label in ("Last follow-up note", "Later than a week"):
        assert f"['{label}'" in i18n, f"{label} has no Chinese translation"


def check_the_panel_grid_follows_the_panel_width() -> None:
    threshold = re.search(r"@container panel \(min-width: (\d+)px\)", CSS)
    assert threshold, (
        "the two-column edit layout is decided by the window, so the ~420px "
        "panel in table view is split in half as well"
    )
    # Measured in the browser: the panel's own content box is 664px wide in
    # list view and 380px in table view, so the threshold has to sit between
    # them. 700px reads the window's number and never fires; 300px fires in
    # the narrow panel and puts the form in half of 380px.
    assert 380 < int(threshold.group(1)) <= 664, (
        f"a {threshold.group(1)}px threshold does not separate the 664px "
        "panel from the 380px one"
    )
    assert "container-name: panel" in CSS
    assert "@media (min-width: 1180px) {\n  .app.detail-open[data-workbench] .followup-panel-grid" not in CSS
    for cell in ("wb-cell-id", "wb-cell-stage", "wb-cell-date"):
        assert f".wb-table-panel .{cell}" in CSS, (
            f"{cell} has no width rule, so it folds one character per line"
        )
    # Compact has to mean the same thing in both views.
    compact_table = '.module[data-density="compact"] .wb-table-panel'
    assert CSS.count(compact_table) >= 2, (
        "compact only reshapes the list, so the compact table kept four-line "
        "customer names and the switch looked like it did nothing"
    )


def check_the_module_has_both_views_and_its_switches() -> None:
    for marker, why in (
        ('id="followup-cards"', "the list has nowhere to render"),
        ('id="followup-table-body"', "the table view has no body"),
        ('id="followup-view-switch"', "there is no way to switch views"),
        ('id="followup-density-switch"', "there is no way to change density"),
        ('class="wb-list-panel"', "the list is not in a panel of its own"),
        ('class="wb-table-panel"', "the table is not in a panel of its own"),
    ):
        assert marker in MODULE, f"{marker} is missing: {why}"
    # One region, two ways of looking at it - never both at once.
    assert '.module[data-view="table"] .wb-list-panel' in CSS
    assert '.module:not([data-view="table"]) .wb-table-panel { display: none; }' in CSS


def check_the_scripts_load_in_order() -> None:
    order = [INDEX.index(f"modules/{name}.js") for name in
             ("cards", "worklist-workbench", "worklist-rows",
              "followup-workbench-rows", "followup-workbench",
              "sales-worklists")]
    assert order == sorted(order), (
        "the workbench is loaded after the list that calls it, or before the "
        "row renderer it uses"
    )


def check_the_panel_becomes_a_column_and_gives_way_on_narrow_screens() -> None:
    for rule, why in (
        (".app.detail-open[data-workbench] .detail-panel { width: var(--wb-panel-width); }",
         "the panel does not take the width beside the list"),
        ("--wb-panel-width: calc(100vw",
         "the panel width is a percentage again, which resolves differently "
         "per property and once let the head run underneath the panel"),
        ("top: var(--wb-panel-top, 0px);",
         "the panel starts at the top of the window, so the head and filters "
         "are squeezed into the selector column"),
        ("@media (max-width: 1180px) {\n  /* Not enough room",
         "there is no fallback for screens too narrow for two panes"),
    ):
        assert rule in CSS, f"{why}"
    # The list keeps a readable width instead of being squeezed by the panel.
    assert 'max-width: var(--wb-list-width);' in CSS
    assert '--wb-list-width: 380px;' in CSS


def check_the_activity_order_is_not_grouped_away() -> None:
    """Grouping by due date is only honest while the sort is by due date.
    Under an activity-time filter the list's order is the answer, so the page
    must ask for the ungrouped shape rather than cutting that order up."""
    source = (ROOT / "frontend" / "js" / "modules" / "sales-worklists.js")
    text = source.read_text(encoding="utf-8")
    assert "groupByDueDate: activity.mode === 'all'" in text, (
        "the follow-up list does not tell the workbench which order it is in, "
        "so an activity-time sort gets cut into due-date groups"
    )
    workbench = (ROOT / "frontend" / "js" / "modules"
                 / "followup-workbench.js").read_text(encoding="utf-8")
    assert "options.groupByDueDate === false" in workbench, (
        "the workbench groups by due date no matter what order it was handed"
    )


def check_the_list_passes_both_amounts_as_the_lead_carries_them() -> None:
    """The shared card mapping answers 0 for "no deal amount". Read straight,
    that 0 stood in the money column of a lead estimated at 210,000, and the
    estimate beside it went unused. The follow-up list has to pass both
    numbers the way the lead holds them."""
    source = (ROOT / "frontend" / "js" / "modules" / "sales-worklists.js")
    text = source.read_text(encoding="utf-8")
    block = text[text.index("async function loadFollowup"):text.index("const plannedMode")]
    for field in ("deal_amount", "estimated_value"):
        assert f"{field}: lead.{field} ?? null" in block, (
            f"{field} is not passed as the lead carries it, so a missing "
            "amount and a real zero reach the row as the same 0"
        )
    # A count of 0 means none; an amount of 0 means zero money, which is not
    # the same as no amount at all.
    for field in ("deal_amount", "estimated_value"):
        assert f"{field}: lead.{field} || 0" not in block, (
            f"{field} flattened with `|| 0` cannot be told from a real zero"
        )


def check_the_row_keeps_the_fields_a_reader_needs() -> None:
    rows = (ROOT / "frontend" / "js" / "modules" / "followup-workbench-rows.js").read_text(encoding="utf-8")
    for marker, why in (
        ("data-inquiry-card", "selection would not go through the production contract"),
        ('data-card-context="followup"', "the panel would open on the wrong tab"),
        ("wb-company", "the customer is not shown"),
        ("wb-next", "what is due is not shown"),
        ("wb-last", "the last follow-up is not shown"),
        ("wb-amount", "the amount is not shown"),
        ("wb-stage", "the progress is not shown"),
        ('tabindex="0"', "the row cannot be reached by keyboard"),
    ):
        assert marker in rows, f"{marker}: {why}"
    # Amounts go through the shared per-currency formatter rather than a rule
    # of the row's own - that is where the zero-versus-missing distinction and
    # the "no currency" label live.
    assert "MoneyTotals.text" in rows, (
        "the row formats money itself instead of using the shared tool"
    )
    assert not re.search(r"\breduce\b|\bsum\(", rows), (
        "the row is adding amounts up, which cannot be done across currencies"
    )
    assert "'USD'" not in rows and '"USD"' not in rows, (
        "the row still has a dollar default to fall back on"
    )
    # The list needs the lead's own amount, so the mapping has to carry it.
    navigation = (ROOT / "frontend" / "js" / "modules" / "lead-navigation.js").read_text(encoding="utf-8")
    worklists = (ROOT / "frontend" / "js" / "modules" / "sales-worklists.js").read_text(encoding="utf-8")
    assert "estimated_value" in worklists, (
        "the follow-up row asks for the estimated value but nothing maps it in"
    )
    assert "quality_rating" in navigation


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// The real date model and the real money formatter. A stub that answered with
// strings is exactly what hid the grouping defect: calendarDay() returns a
// local Date, and comparing it as text put overdue, today and a month away all
// in "next 7 days".
const context = {
  console,
  escapeHtml: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'),
  formatDate: value => `formatted:${value}`,
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.replaceAll(`{${key}}`, value), text),
    locale: () => 'en-US' },
};
context.window = context;
vm.createContext(context);
for (const file of ['followup-filter-model.js', 'money-totals-view.js',
                    'followup-workbench-rows.js']) {
  vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`, 'utf8'), context);
}
const { row, tableRow, bucketOf, moneyText, BUCKETS } = context.FollowupRows;

// Dates are built inside the same realm as the module under test. A Date made
// out here is not `instanceof Date` in there, and calendarDay() would fall
// through to its string branch - a page has one realm, so a test that hands in
// a foreign Date is testing something the browser never does.
const makeDate = vm.runInContext(
  '(function (parts) { return new Date(...parts); })', context);

// ---- which group a lead belongs to -------------------------------------
const now = makeDate([2026, 8, 9, 14, 30]);        // 2026-09-09, local
const bucket = date => bucketOf({ next_followup_date: date }, now);
assert.equal(bucket('2026-09-08'), 'overdue', 'yesterday is not overdue');
assert.equal(bucket('2026-09-09'), 'today', 'today is not today');
assert.equal(bucket('2026-09-10'), 'week');
assert.equal(bucket('2026-09-15'), 'week', 'the seventh day is outside the week');
assert.equal(bucket('2026-09-16'), 'beyond', 'the eighth day is still "this week"');
assert.equal(bucket('2026-10-09'), 'beyond', 'a month away is still "this week"');
assert.equal(bucket(null), 'later');
assert.equal(bucket(''), 'later');
// Nothing is dropped, and "later than a week" is not "no date set".
assert.ok(BUCKETS.some(item => item.key === 'beyond'));
assert.notEqual(BUCKETS.find(item => item.key === 'beyond').label,
  BUCKETS.find(item => item.key === 'later').label);

// A local evening in Asia and a local morning in Europe are the same day here:
// the comparison is on local calendar days, not a UTC slice of the clock.
const lateEvening = makeDate([2026, 8, 9, 23, 30]);
assert.equal(bucketOf({ next_followup_date: '2026-09-09' }, lateEvening), 'today',
  'the local day was taken from a UTC slice, so late evening became tomorrow');
const earlyMorning = makeDate([2026, 8, 9, 0, 30]);
assert.equal(bucketOf({ next_followup_date: '2026-09-08' }, earlyMorning), 'overdue');

// ---- what the amount says ---------------------------------------------
const money = item => moneyText(item);
assert.equal(money({}), 'not quoted', 'nothing recorded should say so');
assert.ok(/EUR 0/.test(money({ estimated_value: 0, currency: 'EUR' })),
  `a deal priced at zero read as unpriced: ${money({ estimated_value: 0, currency: 'EUR' })}`);
assert.ok(/EUR/.test(money({ estimated_value: 42000, currency: 'EUR' })));
assert.ok(!/USD/.test(money({ deal_amount: 10, currency: '' })),
  'a missing currency was filled in with dollars');
assert.ok(/no currency/.test(money({ deal_amount: 10, currency: '' })),
  `a missing currency is not said: ${money({ deal_amount: 10, currency: '' })}`);
// A closed amount wins over the estimate, but only when it is actually there.
assert.ok(/EUR 9/.test(money({ deal_amount: 9000, estimated_value: 42000, currency: 'EUR' })));
assert.ok(/EUR 42/.test(money({ deal_amount: null, estimated_value: 42000, currency: 'EUR' })));
assert.ok(/EUR 0/.test(money({ deal_amount: 0, estimated_value: 42000, currency: 'EUR' })),
  'a deal closed at zero was replaced by the estimate');
// An estimate is not an agreed amount. Printed the same way, a 210,000
// estimate reads as money already booked.
assert.ok(/Est\./.test(money({ estimated_value: 210000, currency: 'SEK' })),
  `an estimate is printed as a deal: ${money({ estimated_value: 210000, currency: 'SEK' })}`);
assert.ok(/Deal/.test(money({ deal_amount: 210000, currency: 'SEK' })),
  `a booked amount is not marked: ${money({ deal_amount: 210000, currency: 'SEK' })}`);

// Both views say the same thing about the same lead.
for (const item of [
  {}, { estimated_value: 0, currency: 'EUR' }, { deal_amount: 10, currency: '' },
  { estimated_value: 42000, currency: 'EUR' },
]) {
  const listed = row({ id: 'l', ...item });
  const tabled = tableRow({ id: 'l', ...item });
  const said = moneyText(item);
  assert.ok(listed.includes(context.escapeHtml(said)), `list: ${said}`);
  assert.ok(tabled.includes(context.escapeHtml(said)), `table: ${said}`);
}

// ---- the row still carries what a reader needs ------------------------
const lead = {
  id: 'lead-1', inquiry_id: 'JPT-1', company_name: '<b>High</b> & Co',
  contact_name: 'Marie', country: 'France', stage: 'Following',
  quality_rating: 'A', quality_issue_count: 2,
  latest_follow_up_at: '2026-08-30', latest_follow_up_summary: 'Asked for <script>',
  next_followup_date: '2026-09-09', estimated_value: 42000, currency: 'EUR',
};
const html = row(lead);
assert.ok(html.includes('data-inquiry-card'), html.slice(0, 200));
assert.ok(html.includes('data-inquiry-id="lead-1"'));
assert.ok(html.includes('data-card-context="followup"'));
assert.ok(!html.includes('<b>High</b>'), 'the customer name was written as markup');
assert.ok(html.includes('&lt;b&gt;High&lt;/b&gt; &amp; Co'), html.slice(0, 400));
assert.ok(!html.includes('<script>'), 'a follow-up summary carried a script tag through');
assert.ok(/<span class="wb-company" data-business>/.test(html),
  'the customer name is not marked as business text, so translation may reword it');
assert.ok(row({ id: 'l2', company_name: 'Nobody', stage: 'Quoted' }).includes('not set'));
assert.ok(row({ id: 'l2', company_name: 'Nobody' }).includes('No formal follow-up'));

// The table's own columns: the note column is the last follow-up's content and
// says so - it used to sit under a "next step" heading.
const table = tableRow(lead);
assert.ok(table.includes('data-inquiry-card') && table.includes('data-inquiry-id="lead-1"'));
assert.ok(table.includes('tabindex="0"'), 'a table row cannot be reached by keyboard');
assert.ok(table.includes('Asked for &lt;script&gt;'));
assert.ok(/class="wb-cell-id"/.test(table) && /class="wb-cell-stage"/.test(table),
  'the fixed-meaning columns have no class to keep them on one line');

// ---- grouping must not overrule the order it was handed ----------------
// The filters promise an order (under "never followed up", the longest wait
// first). Grouping by due date and then printing the groups in a fixed order
// would quietly re-sort across groups, so the groups appear in the order their
// first lead does and the leads keep their order inside a group.
const nodes = {};
const element = id => (nodes[id] ||= {
  id, innerHTML: '', hidden: false, children: [],
  classList: { toggle() {}, contains: () => false },
  setAttribute() {}, getBoundingClientRect: () => ({ top: 120 }),
  querySelectorAll: () => [],
  style: { properties: {}, setProperty(name, value) { this.properties[name] = value; } },
  dataset: {},
});
context.document = {
  getElementById: element,
  querySelector: selector => (selector.includes('wb-layout') ? element('layout') : null),
  querySelectorAll: () => [],
  addEventListener() {},
};
context.WorklistCards = { bind() {}, emptyState: () => '<empty>' };
context.addEventListener = () => {};
context.ResizeObserver = undefined;
// The shell first: the follow-up module asks it for its instance on load.
for (const file of ['worklist-workbench.js', 'followup-workbench.js']) {
  vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`, 'utf8'), context);
}

// The workbench reads "now" itself, so these are counted from today rather
// than written down: fixed dates made this pass until the day the earliest of
// them arrived, and then failed for a reason that had nothing to do with
// grouping.
const dueIn = offset => {
  const when = new Date();
  when.setDate(when.getDate() + offset);
  return when.toISOString().slice(0, 10);
};
const sorted = [
  { id: 'waited-longest', company_name: 'A', next_followup_date: dueIn(3) },
  { id: 'overdue-but-fresh', company_name: 'B', next_followup_date: dueIn(-19) },
  { id: 'also-later', company_name: 'C', next_followup_date: dueIn(4) },
];
// What is asserted is the order, not the label.
context.FollowupWorkbench.render(sorted);
const listHtml = element('followup-cards').innerHTML;
const order = [...listHtml.matchAll(/data-inquiry-id="([^"]+)"/g)].map(match => match[1]);
assert.deepEqual(order, ['waited-longest', 'also-later', 'overdue-but-fresh'],
  `grouping re-sorted the list it was handed: ${order}`);
const groups = [...listHtml.matchAll(/<span>([^<]+)<\/span>\s*<em>(\d+)<\/em>/g)]
  .map(match => [match[1], Number(match[2])]);
assert.equal(groups.length, 2, `${groups.length} groups for two buckets`);
assert.equal(groups[0][1], 2, 'the first group does not hold both later leads');

// The table keeps the plain order it was handed.
const tableOrder = [...element('followup-table-body').innerHTML
  .matchAll(/data-inquiry-id="([^"]+)"/g)].map(match => match[1]);
assert.deepEqual(tableOrder, sorted.map(item => item.id));

// ---- the activity-time order survives the due-date groups -------------
// "Inactive 30+ days" sorts by how long a lead has been quiet, and that order
// IS the answer to the question the reader asked. Grouping it by due date
// moved a lead up two places (measured on real data: D,B,G,C,E became
// D,G,B,C,E) and printed "overdue" last, so in that mode the list is not
// grouped - it keeps the sort's order under one heading that names it.
vm.runInContext(fs.readFileSync('frontend/js/modules/worklist-sort.js', 'utf8'), context);
const day = shift => {
  const date = new Date();
  date.setDate(date.getDate() + shift);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
    + `-${String(date.getDate()).padStart(2, '0')}`;
};
const mixed = [
  { id: 'quiet-400', company_name: 'A', next_followup_date: day(30), activity_date: day(-400) },
  { id: 'quiet-180', company_name: 'B', next_followup_date: day(0), activity_date: day(-180) },
  { id: 'quiet-100', company_name: 'C', next_followup_date: day(5), activity_date: day(-100) },
  { id: 'quiet-50', company_name: 'D', next_followup_date: day(25), activity_date: day(-50) },
  { id: 'quiet-2', company_name: 'E', next_followup_date: day(-7), activity_date: day(-2) },
  { id: 'no-date', company_name: 'F', next_followup_date: null, activity_date: day(-300) },
];
const readingOrder = () => [...element('followup-cards').innerHTML
  .matchAll(/data-inquiry-id="([^"]+)"/g)].map(match => match[1]);

const byActivity = context.WorklistSort.followup(mixed, { activityMode: '30' });
context.FollowupWorkbench.render(byActivity, {}, { groupByDueDate: false });
assert.deepEqual(readingOrder(), byActivity.map(item => item.id),
  `the activity-time order was reshuffled: ${readingOrder()}`);
const heading = element('followup-cards').innerHTML.match(/<span>([^<]+)<\/span>/);
assert.ok(/without activity/i.test(heading[1]),
  `the order is not named, so it reads as an arbitrary list: ${heading[1]}`);
assert.equal((element('followup-cards').innerHTML.match(/wb-group/g) || []).length, 1,
  'the activity-time list is still cut into due-date groups');

// And this is why the guard exists: grouping that same order does change it.
context.FollowupWorkbench.render(byActivity, {}, { groupByDueDate: true });
assert.notDeepEqual(readingOrder(), byActivity.map(item => item.id),
  'grouping no longer reorders anything, so this guard is testing nothing');

// In the default mode the sort is by due date, so the groups agree with it
// and grouping is only a heading - the order is the sort's, unchanged.
const byDueDate = context.WorklistSort.followup(mixed, { activityMode: 'all' });
context.FollowupWorkbench.render(byDueDate, {}, { groupByDueDate: true });
assert.deepEqual(readingOrder(), byDueDate.map(item => item.id),
  `due-date groups re-sorted the due-date order: ${readingOrder()}`);

// Nothing to show: one message, and neither view left on screen beside it.
context.FollowupWorkbench.render([], { title: 'No records in this view' });
assert.equal(element('followup-state').innerHTML, '<empty>');
assert.equal(element('followup-state').hidden, false);
assert.equal(element('layout').hidden, true, 'the views stayed beside the message');
assert.equal(element('followup-cards').innerHTML, '');
assert.equal(element('followup-table-body').innerHTML, '');
"""



def main() -> None:
    check_the_module_has_both_views_and_its_switches()
    check_the_empty_state_is_visible_in_both_views()
    check_the_table_column_says_what_it_shows()
    check_the_panel_grid_follows_the_panel_width()
    check_the_scripts_load_in_order()
    check_the_panel_becomes_a_column_and_gives_way_on_narrow_screens()
    check_the_activity_order_is_not_grouped_away()
    check_the_list_passes_both_amounts_as_the_lead_carries_them()
    check_the_row_keeps_the_fields_a_reader_needs()
    result = subprocess.run(
        ["node", "-e", HARNESS], cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    print("PASS: the follow-up list selects, the panel works, and the row still says what it must")


if __name__ == "__main__":
    main()
