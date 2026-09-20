"""One line of time, one open form, and reordering as a thing you ask for.

The route zone used to hold three readings of the same trip: a day board, a
column of stop forms and a column of leg forms. A reader had to join them up
themselves, and every stop's form was open whether or not anyone was editing
it - twenty stops, twenty forms, one of which mattered.

Now the timeline is the reading surface and the panel beside it holds exactly
the object chosen on it. Three rules make that safe, and they are tested here
rather than described:

  * Choosing is reading. It opens no other zone, saves nothing, marks nothing
    unsaved, and the panel shows one object - the one that was chosen.
  * The timeline is read by date, so Up and Down are not on it. They live in a
    reorder list somebody opens on purpose, where the order is the plan's own.
  * In that list, order and filter are ways of looking: they never rewrite the
    plan and never drop a row from the page, and Up/Down are switched off (with
    a reason) outside plan order rather than moving a stop against a list that
    is not the plan's.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"


# A DOM small enough to read, real enough to run the modules against the markup
# the renderers actually produce. Building the rows by hand here would test the
# test: the point is that what apply() looks for is what render() writes.
DOM = r"""
const VOID = new Set(['input', 'br', 'img', 'hr', 'meta', 'link']);
const TAG = /<(\/)?([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^>])*?)(\/)?>|([^<]+)/g;
const ATTR = /([\w:.-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;

// A browser hands back the decoded value, so a key written into the markup as
// c1&gt;c2 is read as c1>c2 - which is the whole point of matching a rendered
// row against the leg it stands for.
const decode = value => String(value)
  .replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&quot;', '"')
  .replaceAll('&#039;', "'").replaceAll('&amp;', '&');

function attributes(source) {
  const found = {};
  let match;
  while ((match = ATTR.exec(source || ''))) {
    found[match[1]] = decode(match[2] ?? match[3] ?? match[4] ?? '');
  }
  ATTR.lastIndex = 0;
  return found;
}

class El {
  constructor(tag, attrs = {}) {
    this.tagName = String(tag).toUpperCase();
    this.attrs = attrs;
    this.children = [];
    this.parent = null;
    this.style = {};
    this.text = '';
    this.disabled = 'disabled' in attrs;
    this.value = attrs.value ?? '';
    this.checked = 'checked' in attrs;
  }
  get id() { return this.attrs.id || ''; }
  get hidden() { return this.attrs.hidden === true || this.attrs.hidden === ''; }
  set hidden(value) { if (value) this.attrs.hidden = true; else delete this.attrs.hidden; }
  get title() { return this.attrs.title || ''; }
  set title(value) { this.attrs.title = value; }
  focus() { this.focused = true; }
  scrollIntoView() {}
  getAttribute(name) { return name in this.attrs ? String(this.attrs[name]) : null; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  get dataset() {
    const data = {};
    Object.entries(this.attrs).forEach(([name, value]) => {
      if (!name.startsWith('data-')) return;
      data[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
    });
    return data;
  }
  get classList() {
    const names = () => String(this.attrs.class || '').split(/\s+/).filter(Boolean);
    const write = list => { this.attrs.class = [...new Set(list)].join(' '); };
    return {
      contains: name => names().includes(name),
      add: name => write([...names(), name]),
      remove: name => write(names().filter(item => item !== name)),
      toggle: (name, force) => {
        const on = force === undefined ? !names().includes(name) : !!force;
        return on ? write([...names(), name]) : write(names().filter(item => item !== name));
      },
    };
  }
  // What a reader would see: the parser hangs each run of text on the element
  // it sits in, so the whole subtree's text is the concatenation of those.
  get textContent() {
    return this.children.reduce((all, child) => all + child.textContent, this.text || '');
  }
  set textContent(value) { this.text = String(value); this.children = []; this.html = ''; }
  get innerHTML() { return this.html || ''; }
  set innerHTML(value) {
    this.html = String(value);
    this.children = parse(this.html, this);
  }
  descendants() {
    return this.children.flatMap(child => [child, ...child.descendants()]);
  }
  matches(selector) {
    return selector.trim().split(/(?=[.#\[])/).every(part => {
      if (part.startsWith('#')) return this.id === part.slice(1);
      if (part.startsWith('.')) return this.classList.contains(part.slice(1));
      if (part.startsWith('[')) {
        const [name, value] = part.slice(1, -1).split('=');
        const wanted = value ? value.replace(/^["']|["']$/g, '') : null;
        const has = name in this.attrs;
        return wanted === null ? has : has && String(this.attrs[name]) === wanted;
      }
      return this.tagName === part.toUpperCase();
    });
  }
  querySelectorAll(selector) {
    const steps = selector.trim().split(/\s+(?![^\[]*\])/);
    let pool = this.descendants();
    steps.forEach((step, index) => {
      pool = pool.filter(node => node.matches(step));
      if (index < steps.length - 1) pool = pool.flatMap(node => node.descendants());
    });
    return pool;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function parse(html, parent) {
  const stack = [{ node: parent, children: [] }];
  let match;
  TAG.lastIndex = 0;
  while ((match = TAG.exec(html))) {
    const [, closing, tag, attrs, selfClosing, text] = match;
    if (text !== undefined) {
      const top = stack[stack.length - 1];
      if (top.node) top.node.text += text.trim() ? text : '';
      continue;
    }
    if (closing) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    const element = new El(tag, attributes(attrs));
    const top = stack[stack.length - 1];
    element.parent = top.node;
    // Nested frames carry their node's own children array, so one push is one
    // child: pushing again would make every descendant appear twice.
    top.children.push(element);
    if (!selfClosing && !VOID.has(tag.toLowerCase())) stack.push({ node: element, children: element.children });
  }
  return stack[0].children;
}

function makeDocument(roots) {
  const holder = new El('body');
  roots.forEach(id => { const node = new El('div', { id }); node.parent = holder; holder.children.push(node); });
  return {
    body: holder,
    getElementById: id => holder.descendants().find(node => node.id === id) || null,
    querySelectorAll: selector => holder.querySelectorAll(selector),
    querySelector: selector => holder.querySelector(selector),
    addEventListener() {},
  };
}
"""

HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

__DOM__

const ctx = {
  console, assert,
  escapeHtml: value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;'),
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
  document: makeDocument(['trip-current-plan', 'trip-stop-board', 'trip-plan-headline',
                          'trip-stop-order-list', 'trip-schedule-list', 'trip-timeline-toolbar',
                          'trip-schedule-status']),
  addEventListener() {},
  Date,
  TripDuration: {
    toDisplayDays: value => value, readStopDuration: stop => stop.stay_days ?? 1,
    toDisplayTravelDays: value => value, label: value => `${value}`,
  },
  TripPlanningDraft: { durationFor: (id, value) => value, get: () => ({ legOverrides: {} }),
                       MODES: ['flight', 'drive', 'ground_public', 'other'] },
  TripCandidateState: { warningText: value => value },
  TripZones: { renderHeader() {} },
};
ctx.window = ctx;
ctx.State = { currentTripPlan: null };
vm.createContext(ctx);
for (const file of ['trip-stop-schedule-controls.js', 'trip-stop-board.js',
                    'trip-stop-board-view.js', 'trip-stop-card.js', 'trip-stop-order-view.js',
                    'trip-selection.js', 'trip-team-timeline-view.js', 'trip-team-timeline.js',
                    'trip-timeline-model.js', 'trip-timeline-view.js',
                    'trip-leg-rows.js', 'trip-leg-card.js', 'trip-transport-view.js',
                    'trip-detail-panel.js', 'trip-itinerary-view.js']) {
  vm.runInContext(fs.readFileSync(`frontend/js/modules/${file}`, 'utf8'), ctx, { filename: file });
}
const { TripStopBoard, TripSelection, document: doc } = ctx;
const rows = () => doc.querySelectorAll('#trip-stop-order-list .trip-order-row[data-stop-id]');
const row = id => rows().find(node => node.dataset.stopId === id);
const detail = () => doc.getElementById('trip-current-plan');
const entries = () => doc.querySelectorAll('#trip-schedule-list .trip-team-entry[data-id]');
const draw = () => {
  ctx.TripTransportView.render(ctx.State.currentTripPlan, ctx.TripPlanningDraft.get());
  ctx.TripTimelineView.render(ctx.State.currentTripPlan, doc.getElementById('trip-schedule-list'));
  ctx.renderCurrentTripPlan();
};

// One agreed visit, one still movable, one with no date at all, and a hotel.
const plan = { id: 'p1', planning_mode: 'team', members: [{ user_id: 'u1', display_name: 'Anna Berg' }],
  stops: [
    { id: 'c1', stop_kind: 'customer', sequence_no: 1, customer_name: 'Berlin Optics',
      city: 'Berlin', country: 'DE', planned_date: '2026-09-20', planned_start_period: 'AM',
      schedule_locked: true, stay_days: 1 },
    { id: 'c2', stop_kind: 'customer', sequence_no: 2, customer_name: 'Lyon Lasers',
      city: 'Lyon', country: 'FR', planned_date: '2026-09-22', stay_days: 1 },
    { id: 'c3', stop_kind: 'customer', sequence_no: 3, customer_name: 'Porto Photonics',
      city: 'Porto', country: 'PT', stay_days: 1 },
    { id: 'f1', stop_kind: 'free', sequence_no: 4, location_name: 'Hamburg hotel',
      category: 'hotel', planned_date: '2026-09-21', stay_days: 1 },
  ],
  legs: [{ leg_key: 'c1>c2', member_id: 'u1', from_label: 'Berlin', to_label: 'Lyon',
    selected_mode: 'drive', distance_km: 1100, time_hours: 11, travel_half_days: 2,
    planned_start_date: '2026-09-21', planned_start_period: 'AM',
    planned_end_date: '2026-09-21', planned_end_period: 'PM' }],
  schedule_items: [
    { member_id: 'u1', item_type: 'customer', source_id: 'c1', date: '2026-09-20', period: 'AM', lane_order: 1, title: 'Berlin Optics' },
    { member_id: 'u1', item_type: 'leg', source_id: 'c1>c2', date: '2026-09-21', period: 'AM', lane_order: 1, title: 'Berlin -> Lyon', selected_mode: 'drive' },
    { member_id: 'u1', item_type: 'free', source_id: 'f1', date: '2026-09-21', period: 'PM', lane_order: 2, title: 'Hamburg hotel' },
    { member_id: 'u1', item_type: 'customer', source_id: 'c2', date: '2026-09-22', period: 'AM', lane_order: 1, title: 'Lyon Lasers' },
  ] };
ctx.State.currentTripPlan = plan;
draw();

// 1. The timeline reads by day, and a day holds its half-days.
const days = doc.querySelectorAll('#trip-schedule-list .trip-day');
assert.equal(days.length, 4, "the days of the trip are not the timeline's first level");
assert.deepEqual(days.slice(0, 3).map(day => day.dataset.day),
  ['2026-09-20', '2026-09-21', '2026-09-22']);
assert.equal(doc.querySelectorAll('#trip-schedule-list .trip-team-slot').length, 4);
assert.ok(days[3].textContent.includes('Porto Photonics'),
  'a stop with no date was dropped instead of being listed as not scheduled');
assert.ok(days[0].textContent.includes('Sunday'), 'the day does not say which weekday it is');

// 2. Nothing is chosen to begin with, and the panel says what to do.
assert.ok(detail().innerHTML.includes('Choose a visit or a journey'), detail().innerHTML);
assert.equal(detail().querySelectorAll('.trip-stop').length, 0,
  'a form was opened before anybody asked for one');

// 3. Choosing a visit opens that visit's form - and only that one.
TripSelection.select('stop', 'c2');
const cards = detail().querySelectorAll('.trip-stop[data-stop-id]');
assert.equal(cards.length, 1, 'the panel holds more than the one chosen stop');
assert.equal(cards[0].dataset.stopId, 'c2');
['stop-stay-c2', 'stop-agreed-date-c2', 'stop-agreed-period-c2', 'stop-period-c2',
 'stop-confirmation-c2', 'stop-schedule-lock-c2', 'stop-purpose-c2'].forEach(id =>
   assert.ok(detail().innerHTML.includes(`id="${id}"`), `the visit form lost ${id}`));
assert.ok(detail().innerHTML.includes('saveTripStopResult'));
// What happened on the visit is recorded where the fields for it are - this
// card plans, it does not report.
assert.ok(!detail().innerHTML.includes('id="stop-result-c2"'),
  'the planning card offers a result nobody can save from here');
assert.ok(detail().innerHTML.includes('TripRouteFocus.goToVisitRecord'),
  'there is no way from the plan to the place the visit is recorded');
assert.ok(detail().innerHTML.includes('TripRouteFocus.goToVisit'),
  'there is no way from the chosen visit to its preparation');
ctx.TripTimelineView.mark();
const chosen = entries().filter(entry => entry.classList.contains('is-selected'));
assert.equal(chosen.length, 1);
assert.equal(chosen[0].dataset.id, 'c2');

// 4. Choosing a journey swaps the form: still one object, now the leg's.
TripSelection.select('leg', 'c1>c2', { memberId: 'u1' });
assert.equal(detail().querySelectorAll('.trip-stop[data-stop-id]').length, 0,
  "the visit's form stayed open under the journey's");
const legCard = detail().querySelectorAll('.trip-leg-card[data-leg-key]');
assert.equal(legCard.length, 1);
assert.equal(legCard[0].dataset.legKey, 'c1>c2');
assert.ok(detail().innerHTML.includes('id="trip-leg-mode-0"'), 'the journey has no mode control');
assert.ok(detail().innerHTML.includes('2026-09-21'), 'the journey does not say when it runs');
assert.ok(detail().innerHTML.includes('trip-leg-suggestions-0'),
  'travel options have nowhere to arrive on the chosen journey');

// 5. A stop removed elsewhere takes its form with it, rather than leaving one
//    open on something that is no longer in the plan.
TripSelection.select('stop', 'c3');
ctx.State.currentTripPlan = { ...plan, stops: plan.stops.filter(stop => stop.id !== 'c3') };
ctx.renderCurrentTripPlan();
assert.equal(TripSelection.get(), null, 'the selection outlived the stop it pointed at');
assert.ok(detail().innerHTML.includes('Choose a visit or a journey'));
ctx.State.currentTripPlan = plan;
draw();

// 6. Reordering is its own list, in the plan's own order, with Up and Down.
assert.equal(rows().length, 4);
assert.equal(rows().map(item => item.dataset.stopId).join(','), 'c1,c2,c3,f1');
assert.equal(doc.querySelectorAll('#trip-schedule-list [data-move]').length, 0,
  'Up and Down are on the timeline, where "down" has no meaning');

// 7. Sorting that list is a way of looking: the plan keeps its order, every row
//    stays on the page, and the undated stop reads last rather than first.
TripStopBoard.setOrder('date');
assert.equal(plan.stops.map(stop => stop.id).join(','), 'c1,c2,c3,f1', 'sorting rewrote the plan');
assert.equal(rows().length, 4);
assert.deepEqual(['c1', 'f1', 'c2', 'c3'].map(id => Number(row(id).style.order)), [0, 1, 2, 3]);

// 8. Moving a stop against a list that is not the plan's is refused, and says
//    how to get the buttons back.
const moves = id => row(id).querySelectorAll('[data-move]');
assert.ok(moves('c2').every(button => button.disabled), 'a stop could be moved out of plan order');
assert.match(moves('c2')[0].title, /plan order/);
TripStopBoard.setOrder('plan');
assert.equal(moves('c2')[0].disabled, false, 'plan order did not give the moves back');
assert.equal(moves('c1')[0].disabled, true, 'the first stop offered to move up');
assert.equal(moves('f1')[1].disabled, true, 'the last stop offered to move down');

// 9. Filtering hides rows; it never removes them. Kind and timing are separate
//    questions, and asking one does not answer the other.
TripStopBoard.setTiming('agreed');
assert.equal(rows().length, 4, 'filtering deleted rows instead of hiding them');
assert.deepEqual(rows().map(item => item.hidden), [false, true, true, true]);
TripStopBoard.setKind('free');
assert.deepEqual(rows().map(item => item.hidden), [true, true, true, true],
  'a hotel with an agreed time is neither, and both filters have to apply');
TripStopBoard.setTiming('all');
assert.equal(row('f1').hidden, false);
assert.ok(doc.getElementById('trip-stop-board').innerHTML.includes('Showing 1 of 4'),
  doc.getElementById('trip-stop-board').innerHTML);
TripStopBoard.setKind('all');

console.log(JSON.stringify({ days: days.length, rows: rows().length }));
"""


def _node(script: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(script)
        path = handle.name
    result = subprocess.run(["node", path], capture_output=True, text=True, cwd=ROOT)
    Path(path).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


def check_the_timeline_and_the_panel_beside_it() -> None:
    output = _node(HARNESS.replace("__DOM__", DOM))
    assert json.loads(output.strip().splitlines()[-1])["rows"] == 4


def check_the_zone_holds_one_reading_of_the_trip() -> None:
    index = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    panel = index[index.index('id="trip-schedule-panel"'):index.index('data-trip-zone="execution"')]
    assert 'id="trip-schedule-list"' in panel and 'id="trip-current-plan"' in panel, (
        "the timeline and the panel for what is chosen on it are not together"
    )
    assert panel.index('id="trip-schedule-list"') < panel.index('id="trip-current-plan"')
    assert 'class="trip-detail-panel"' in panel
    assert 'id="trip-timeline-toolbar"' in panel, "there is no way to choose who or what to read"
    # The second and third readings of the same trip are gone, not hidden.
    for removed in ('id="trip-leg-list"', 'id="trip-leg-board"', 'class="trip-route-workspace"'):
        assert removed not in index, f"{removed} is still a second list of the same trip"
    assert "trip-leg-board.js" not in index and not (MODULES / "trip-leg-board.js").exists(), (
        "the module that filtered the removed leg list is still loaded"
    )
    order_at = index.index('class="review-panel trip-stop-order"')
    assert "<details" in index[order_at - 200:order_at], (
        "the reorder list is open by default again"
    )
    assert 'id="trip-stop-order-list"' in index[order_at:]


def check_the_timeline_owns_the_reading_surface() -> None:
    schedule = (MODULES / "trip-schedule-view.js").read_text(encoding="utf-8")
    assert "TripTimelineView" in schedule, "the schedule view draws its own board again"
    assert "planning_mode === 'team'" not in schedule, (
        "a team plan and a single traveller's plan are drawn by two renderers again"
    )
    timeline = (MODULES / "trip-team-timeline.js").read_text(encoding="utf-8")
    assert "TripTimelineView" in timeline
    detail = (MODULES / "trip-detail-panel.js").read_text(encoding="utf-8")
    assert "TripSelection" in detail and "renderTripStopCard" in detail
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    panel_css = css[css.index(".trip-detail-panel {"):][:300]
    assert "position: sticky" in panel_css, (
        "the panel scrolls away from the line it belongs to"
    )


def main() -> None:
    check_the_timeline_and_the_panel_beside_it()
    check_the_zone_holds_one_reading_of_the_trip()
    check_the_timeline_owns_the_reading_surface()
    print("PASS: one timeline, one open form beside it, and reordering only "
          "where the order is the plan's own")


if __name__ == "__main__":
    main()
