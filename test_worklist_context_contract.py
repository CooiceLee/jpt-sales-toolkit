"""The line pinned above a scrolling list says what this list is actually showing.

The filters are a tall block at the top of the page; scroll into a thousand
rows and nothing on screen says what produced them. The sticky line answers
that - so it has to answer it correctly.

It was reading `filter-owner`, `filter-tech` and `filter-region`, which no
queue has: every queue builds its own `stage-owner-<queue>`, `stage-tech-<queue>`
and `stage-region-<queue>`. Choosing a salesperson and a region changed the
list and not the sentence. Worse, its fallback read `filter-stage` from
anywhere in the page: that select belongs to the inquiry handler and stays in
the document while another queue is open, so a follow-up reader could be told
their list was filtered to "Quoted" by a control their list never consulted.

The follow-up queue's own conditions - which due window, how long since the
last activity, and the custom date range behind "custom" - were not read at all.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// Elements that answer the selectors these modules actually use.
function node(extra = {}) {
  const self = {
    value: '', textContent: '', innerHTML: '', className: '', dataset: {},
    selectedOptions: [], sel: {},
    querySelector(selector) { return self.sel[selector] || null; },
    querySelectorAll() { return []; },
    setAttribute() {}, scrollIntoView() {}, appendChild() {},
    ...extra,
  };
  return self;
}
function select(value, label) {
  return node({ value, selectedOptions: value ? [{ textContent: label }] : [] });
}

const modules = {};
const ctx = {
  console,
  escapeHtml: value => String(value ?? ''),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  document: {
    getElementById: id => modules[id] || null,
    querySelector: () => null,
    createElement: () => node(),
  },
  State: { stageFilters: {}, currentInquiry: null },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/worklist-context.js', 'utf8'),
                ctx, { filename: 'worklist-context.js' });

function queue(key, controls = {}) {
  const layout = node();
  const host = node();
  layout.parentNode = { insertBefore: (row) => { host.sel['.wb-context'] = row; } };
  host.sel['.wb-layout'] = layout;
  Object.entries(controls).forEach(([selector, value]) => { host.sel[selector] = value; });
  modules['module-' + key] = host;
  return host;
}

function summary(key, items = []) {
  ctx.WorklistContext.update(key, items);
  const row = modules['module-' + key].sel['.wb-context'];
  const match = row.innerHTML.match(/class="wb-context-filters" data-business>([^<]*)</);
  return match[1].trim();
}

// The inquiry handler is left in the page with a stage chosen, the way it is
// whenever the reader has been there before opening another queue.
queue('handler', { '#filter-stage': select('Quoted', 'Quoted') });

const answers = {};

// A follow-up list filtered by its own tab, its activity window, a salesperson
// and a region.
queue('followup', {
  '.filters-bar .filter-primary .filter-tab.active[data-filter]':
    node({ textContent: 'Overdue', dataset: { filter: 'overdue' } }),
  '#stage-owner-followup': select('u1', 'Zhang Wei'),
  '#stage-tech-followup': select('', ''),
  '#stage-region-followup': select('EU', 'Europe'),
  '#followup-activity-filter': select('30', 'Inactive 30+ days'),
});
ctx.State.stageFilters = { search: 'ACME' };
answers.followup = summary('followup', [1, 2, 3]);
for (const expected of ['Overdue', 'Zhang Wei', 'Europe', 'Inactive 30+ days',
                        'Search: ACME']) {
  assert.ok(answers.followup.includes(expected),
    `the summary does not mention ${expected}: ${answers.followup}`);
}
assert.ok(!answers.followup.includes('Quoted'),
  'a condition from the hidden inquiry handler was presented as this list\'s: '
  + answers.followup);

// "Custom" on its own does not say which days.
modules['module-followup'].sel['#followup-activity-filter'] = select('custom', 'Custom activity dates');
modules['module-followup'].sel['#followup-activity-from'] = node({ value: '2026-01-01' });
modules['module-followup'].sel['#followup-activity-to'] = node({ value: '2026-03-31' });
answers.custom = summary('followup', [1]);
assert.ok(answers.custom.includes('2026-01-01') && answers.custom.includes('2026-03-31'),
  `the custom activity window is not stated: ${answers.custom}`);

// One customer, reached from the review map: narrower than the search box.
ctx.State.stageFilters = { search: 'ACME Optics', customerId: 'c-7' };
answers.customer = summary('followup', [1]);
assert.ok(answers.customer.includes('Customer: ACME Optics'), answers.customer);
assert.ok(!answers.customer.includes('Search:'),
  'the same customer was stated twice, once as a search and once as a customer');

// Nothing chosen is "no filters" - including the tab that means "everything".
ctx.State.stageFilters = {};
queue('deal', {
  '.filters-bar .filter-primary .filter-tab.active[data-filter]':
    node({ textContent: 'All deals', dataset: { filter: 'all' } }),
  '#stage-owner-deal': select('', ''),
  '#stage-region-deal': select('', ''),
});
answers.empty = summary('deal', []);
assert.equal(answers.empty, 'No filters', answers.empty);

// The handler's own stage is this queue's condition when the handler is the
// queue on screen.
answers.handler = summary('handler', [1, 2]);
assert.ok(answers.handler.includes('Quoted'), answers.handler);
console.log(JSON.stringify(answers));
"""


def check_the_summary_reads_this_queues_own_controls() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    answers = json.loads(result.stdout.strip().splitlines()[-1])
    assert answers["empty"] == "No filters"


def check_the_control_ids_are_the_ones_the_page_builds() -> None:
    """The summary and the controls have to keep naming the same things."""
    view = (MODULES / "stage-filter-view.js").read_text(encoding="utf-8")
    context = (MODULES / "worklist-context.js").read_text(encoding="utf-8")
    for built in ("stage-owner-${moduleKey}", "stage-tech-${moduleKey}",
                  "stage-region-${moduleKey}"):
        read = built.replace("${moduleKey}", "${key}")
        assert built in view, f"{built} is no longer the control the page builds"
        assert read in context, (
            f"the summary does not read {read}, so that condition is missing "
            "from the sentence above the list"
        )
    for stale in ("'filter-owner'", "'filter-tech'", "'filter-region'",
                  "'filter-customer'"):
        assert stale not in context, (
            f"the summary still reads {stale}, which no queue has"
        )
    assert "getElementById(`module-${key}`)" in context, (
        "the summary reads controls from the whole document, so a hidden "
        "queue's condition can be shown as this one's"
    )
    assert 'id="followup-activity-filter"' in INDEX


EMPTY_HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

// The workbench shell, with only the parts it reaches for.
const nodes = {};
const node = () => ({
  innerHTML: '', hidden: false, dataset: {}, style: { setProperty() {} },
  classList: { contains: () => true, add() {}, remove() {}, toggle() {} },
  addEventListener() {}, getBoundingClientRect: () => ({ top: 0, bottom: 0, height: 0 }),
  querySelector: () => null, querySelectorAll: () => [],
});
['module-handler', 'handler-cards', 'handler-table-body', 'handler-state', 'app']
  .forEach(id => { nodes[id] = node(); });

const drawn = [];
const ctx = {
  console,
  requestAnimationFrame: callback => callback(),
  addEventListener() {},
  document: {
    addEventListener() {},
    getElementById: id => nodes[id] || null,
    querySelector: selector =>
      (selector === '#module-handler .wb-layout' ? nodes['module-handler'] : null),
  },
  WorklistCards: { bind() {}, emptyState: () => '<p>nothing</p>' },
  WorklistContext: { update: (key, items) => drawn.push([key, items.length]) },
};
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('frontend/js/modules/worklist-workbench.js', 'utf8'),
                ctx, { filename: 'worklist-workbench.js' });

const shell = ctx.WorklistWorkbench.create('handler');
shell.draw({ items: [{ id: 'a' }, { id: 'b' }], listHtml: '<li>a</li>', tableHtml: '<tr></tr>' });
shell.draw({ items: [], emptyCopy: { title: 'Nothing here' },
             listHtml: '', tableHtml: '' });
assert.deepEqual(drawn, [['handler', 2], ['handler', 0]],
  'the line above the list was not redrawn for the query that emptied it, so '
  + 'it kept the previous count and the previous conditions');
console.log(JSON.stringify({ drawn }));
"""


def check_an_emptied_list_still_says_what_emptied_it() -> None:
    """A filter that returns nothing is when the sentence matters most.

    The summary was written only on the path that draws rows, so choosing a
    stage with no leads left the previous query's "4 shown · New" pinned above
    an empty page: the reader is told there are four of something they cannot
    see, and not which condition removed them.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(EMPTY_HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout


def main() -> None:
    check_the_summary_reads_this_queues_own_controls()
    check_the_control_ids_are_the_ones_the_page_builds()
    check_an_emptied_list_still_says_what_emptied_it()
    print("PASS: the sticky line states this queue's own filters, all of them, "
          "and borrows none from a queue that is not on screen")


if __name__ == "__main__":
    main()
