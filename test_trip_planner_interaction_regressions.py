"""What happens when saves fail, races happen, and other editors hold work.

The rest of the frontend suite checks that the right calls are made from the
right places. These check the moments in between: a save that fails, two saves
in flight at once, a refresh that another editor blocks. Every one of them was
reported as "the screen says it saved and the plan disagrees".
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
MODULES = ROOT / "frontend" / "js" / "modules"
NODE = "node"


HARNESS = """
globalThis.window = globalThis;
globalThis.escapeHtml = value => String(value ?? '');
globalThis.I18n = { t: (key, params = {}) =>
    String(key).replace(/\\{(\\w+)\\}/g, (_, name) => params[name] ?? `{${name}}`) };
globalThis.notes = [];
globalThis.notify = message => notes.push(message);
globalThis.setTripBusy = () => {};
globalThis.handleTripError = async () => {};
globalThis.renderTripPlans = () => {};
globalThis.renderCurrentTripPlan = () => {};
globalThis.renderTripMap = () => {};
globalThis.syncTripPlanListEntry = () => {};
globalThis.populateTripPlanForm = (plan, options) => { populates.push(options || {}); };
globalThis.populates = [];
"""


def _source(path: str) -> str:
    return ROOT.joinpath(path).read_text(encoding="utf-8")


def run(body: str, modules: tuple[str, ...]) -> dict:
    sources = "\n".join(
        (MODULES / name).read_text(encoding="utf-8") for name in modules
    )
    # Wrapped so a top-level await does not make node treat this as a module,
    # where the classic-script globals these files set would not be there.
    script = (
        f"{HARNESS}\n{sources}\n(async () => {{\n{body}\n}})()"
        ".catch(error => { console.error(error); process.exit(1); });"
    )
    try:
        result = subprocess.run(
            [NODE, "-e", script],
            capture_output=True, text=True, check=False, cwd=ROOT, timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise AssertionError(
            "the browser code never settled: something is waiting on an answer "
            "that will not come, which in the app is a button that stays dead"
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip()[:900])
    return json.loads(result.stdout.strip().splitlines()[-1])





def check_a_failed_rename_puts_the_name_back() -> None:
    """A name that did not save does not stay on screen as though it did.

    The title box saves on its own, so a refused save leaves the reader looking
    at a name the plan does not have - and the next thing that redraws the form
    replaces it without a word.
    """
    data = run("""
const field = { value: 'Renamed by hand' };
globalThis.document = { getElementById: id =>
    id === 'trip-title' ? field : null };
globalThis.State = { currentTripPlan: { id: 'p1', title: 'Trip Sept', row_version: 4 } };
globalThis.TripPlanIdentity = {
  intend: () => 1,
  accept: (token, plan) => { State.currentTripPlan = plan; return true; },
};
globalThis.TripPlanningDraft = { adopt: () => { throw new Error('draft touched'); },
  change: () => { throw new Error('draft touched'); } };
globalThis.ApiClient = { updateTripPlan: async () => { throw new Error('conflict'); } };
__RUN__
console.log(JSON.stringify({ shown: field.value, populates: populates.length }));
""".replace("__RUN__", "await TripPlanTitleActions.titleChanged();"),
        ("trip-plan-title-actions.js",))
    assert data["shown"] == "Trip Sept", (
        f"a refused rename must put the saved name back: {data['shown']}"
    )
    assert data["populates"] == 0, (
        "a failed rename must not refill the form from the server, which would "
        "throw away every other unsaved change on it"
    )


def check_renaming_keeps_the_rest_of_the_route_draft() -> None:
    """Saving the name touches the name, and nothing else.

    Refilling the whole form from the server put back the dates, transport
    choices and stop durations the reader had changed and not yet saved.
    """
    data = run("""
const field = { value: 'Trip October' };
globalThis.document = { getElementById: () => field };
globalThis.State = { currentTripPlan: { id: 'p1', title: 'Trip Sept', row_version: 4 } };
globalThis.TripPlanIdentity = {
  intend: () => 1,
  accept: (token, plan) => { State.currentTripPlan = plan; return true; },
};
let changed = null;
globalThis.TripPlanningDraft = {
  adopt: mutate => { const draft = { header: { title: 'Trip Sept', start_date: '2026-09-02' } };
    mutate(draft); changed = draft; },
  change: () => { throw new Error('a saved name must not mark the route unsaved'); },
};
globalThis.ApiClient = { updateTripPlan: async (id, body) =>
  ({ id, title: body.title, row_version: 5 }) };
await TripPlanTitleActions.titleChanged();
console.log(JSON.stringify({
  header: changed?.header, populates, shown: field.value, notes,
}));
""", ("trip-plan-title-actions.js",))
    assert data["populates"] == [], (
        "renaming must not refill the whole form: unsaved route changes on it "
        "would be replaced by the server's older values"
    )
    assert data["header"]["title"] == "Trip October", data["header"]
    assert data["header"]["start_date"] == "2026-09-02", (
        f"the rest of the draft header must survive a rename: {data['header']}"
    )


def check_an_empty_name_is_refused_out_loud() -> None:
    """Clearing the name says so and puts the name back."""
    data = run("""
const field = { value: '   ' };
globalThis.document = { getElementById: () => field };
globalThis.State = { currentTripPlan: { id: 'p1', title: 'Trip Sept', row_version: 4 } };
globalThis.TripPlanIdentity = {
  intend: () => 1,
  accept: (token, plan) => { State.currentTripPlan = plan; return true; },
};
globalThis.TripPlanningDraft = { adopt: () => { throw new Error('nothing to save'); },
  change: () => { throw new Error('nothing to save'); } };
globalThis.ApiClient = { updateTripPlan: async () => { throw new Error('never'); } };
await TripPlanTitleActions.titleChanged();
console.log(JSON.stringify({ shown: field.value, notes }));
""", ("trip-plan-title-actions.js",))
    assert data["shown"] == "Trip Sept", (
        f"an empty name must not be left on screen: {data['shown']}"
    )
    assert data["notes"], "the reader has to be told why the name came back"


def check_member_dates_are_saved_one_at_a_time() -> None:
    """Two dates changed quickly do not answer out of order.

    Sent together, the answers come back in whatever order the server produces
    them, and the earlier answer overwrites the later change - while the box
    goes on showing the newer date.
    """
    data = run("""
const fields = {
  'trip-team-departure-a': { value: '2026-09-20', disabled: false },
  'trip-team-departure-b': { value: '2026-09-21', disabled: false },
};
globalThis.document = { getElementById: id => fields[id] || null };
globalThis.State = { currentTripPlan: { id: 'p1', members: [
  { user_id: 'a', display_name: 'Ayden', departure_date: '2026-09-13', row_version: 2 },
  { user_id: 'b', display_name: 'Slluu', departure_date: '2026-09-13', row_version: 2 },
] } };
const order = [];
let inFlight = 0, overlapped = false;
// The server keeps the plan, so its answer carries every write it has taken -
// not only the one being answered. The browser drops an answer that arrives
// after the reader has asked for something newer, which is safe exactly
// because the newer answer includes the older write.
const stored = { id: 'p1', members: State.currentTripPlan.members.map(m => ({ ...m })) };
globalThis.ApiClient = { setTripMember: async (planId, body) => {
  inFlight += 1;
  if (inFlight > 1) overlapped = true;
  // The first call answers slowly, the second quickly.
  await new Promise(done => setTimeout(done, body.user_id === 'a' ? 30 : 1));
  inFlight -= 1;
  order.push(body.user_id);
  stored.members = stored.members.map(member => member.user_id === body.user_id
    ? { ...member, departure_date: body.departure_date, row_version: 3 } : member);
  return { ...stored, members: stored.members.map(member => ({ ...member })) };
} };
await Promise.all([
  TripTeamActions.departureChanged('a', '2026-09-20'),
  TripTeamActions.departureChanged('b', '2026-09-21'),
]);
console.log(JSON.stringify({ order, overlapped,
  dates: State.currentTripPlan.members.map(m => m.departure_date),
  written: stored.members.map(m => m.departure_date) }));
""", ("trip-plan-identity.js", "trip-team-queue.js",
         "trip-team-actions.js"))
    assert data["overlapped"] is False, (
        "two member saves must not be in flight together, or the slower answer "
        "lands last and undoes the newer change"
    )
    assert data["order"] == ["a", "b"], (
        f"the saves must be answered in the order they were made: {data['order']}"
    )
    assert data["written"] == ["2026-09-20", "2026-09-21"], (
        f"both changes must reach the plan: {data['written']}"
    )
    assert data["dates"] == ["2026-09-20", "2026-09-21"], (
        f"both changes must survive on screen: {data['dates']}"
    )


def check_a_failed_member_date_stops_claiming_it_saved() -> None:
    """A date that did not save goes back to what the plan says."""
    data = run("""
const field = { value: '2026-09-20', disabled: false };
globalThis.document = { getElementById: id =>
  id === 'trip-team-departure-a' ? field : null };
globalThis.State = { currentTripPlan: { id: 'p1', members: [
  { user_id: 'a', display_name: 'Ayden', departure_date: '2026-09-13', row_version: 2 },
] } };
globalThis.ApiClient = { setTripMember: async () => { throw new Error('conflict'); } };
await TripTeamActions.departureChanged('a', '2026-09-20');
console.log(JSON.stringify({ shown: field.value, disabled: field.disabled, notes }));
""", ("trip-plan-identity.js", "trip-team-queue.js",
         "trip-team-actions.js"))
    assert data["shown"] == "2026-09-13", (
        "a refused date must go back to the one the plan holds, or the box "
        f"claims a change the trip does not have: {data['shown']}"
    )
    assert data["disabled"] is False, "the box must be usable again afterwards"
    assert data["notes"], "the reader has to be told the save did not happen"


def check_saving_a_visit_refreshes_even_while_another_editor_is_open() -> None:
    """A saved visit redraws the plan whatever else is being edited.

    Reloading the whole planner stops when another editor holds unsaved work,
    and said nothing when it did - so "saved" appeared over a map and timeline
    still showing the colleagues of the previous calculation.
    """
    source = (MODULES / "trip-briefing-actions.js").read_text(encoding="utf-8")
    assert "await loadTripPlanner();" not in source, (
        "a full reload is stopped by any other unsaved editor, and reports "
        "nothing when it is"
    )
    # And it reads back under the number the screen already had: taking a new
    # one let a late save answer in place of the plan the reader had moved to.
    assert "TripPlanRefresh.reread(planId, { token: session.token })" in source, (
        "the plan has to be read back on its own after a visit is saved, "
        "under the identity that save belongs to"
    )

    data = run("""
globalThis.State = { currentTripPlan: { id: 'p1' } };
globalThis.document = { getElementById: () => null };
// Another editor is holding unsaved work, which stops a whole-planner reload.
globalThis.TripVisitDraft = { guard: () => true };
globalThis.TripBriefingDraft = { guard: () => true };
globalThis.ApiClient = { getTripPlan: async id => ({ id, title: 'Trip Sept',
  members: [], stops: [], schedule_items: [{ member_id: 'a' }] }) };
let drew = 0;
globalThis.renderCurrentTripPlan = () => { drew += 1; };
globalThis.TripScheduleView = { renderPlan: () => { drew += 1; } };
globalThis.TripPlannerModule = { renderVisitExecution: () => { drew += 1; } };
globalThis.renderTripMap = () => { drew += 1; };
const done = await TripPlanRefresh.reread('p1');
console.log(JSON.stringify({ done, drew, items:
  (State.currentTripPlan.schedule_items || []).length }));
""", ("trip-plan-identity.js", "trip-plan-refresh.js"))
    assert data["done"] is True, "re-reading one plan must not be blocked"
    assert data["drew"] >= 4, (
        f"the map, timeline and cards all have to be redrawn: {data['drew']}"
    )
    assert data["items"] == 1, "the redrawn plan is the one just read back"


def check_a_save_holds_the_form_it_took_its_values_from() -> None:
    """Typing while a save is in flight was neither sent nor kept.

    The request carries the values as they were when the button was pressed.
    The fields stayed editable, and the success path cleared the draft and
    closed the editor - so whatever was typed in between went with it, with
    nothing on screen saying so.
    """
    data = run("""
const fields = [];
function field(id) {
  const node = { id, value: '', disabled: false, attributes: {},
    setAttribute(name) { this.attributes[name] = ''; },
    hasAttribute(name) { return name in this.attributes; },
    removeAttribute(name) { delete this.attributes[name]; } };
  fields.push(node);
  return node;
}
const content = field('content');
const addRow = field('add-row');
const editor = {
  hidden: false, innerHTML: '', attributes: {},
  querySelectorAll: () => [content, addRow],
  closest: () => ({ classList: { toggle() {} } }),
  setAttribute() {}, scrollIntoView() {},
};
const byId = { 'trip-briefing-editor': editor };
globalThis.document = {
  getElementById: id => byId[id] || null,
  querySelector: () => null, querySelectorAll: () => [],
  addEventListener() {},
};
globalThis.State = { currentTripPlan: { id: 'plan-a', planning_mode: 'team',
  members: [], stops: [{ id: 'stop-1' }] } };
globalThis.TripZones = { planChanged() {}, renderHeader() {}, current: () => 'briefing' };
globalThis.TripScheduleView = { renderPlan() {} };
globalThis.TripPlannerModule = { renderVisitExecution() {} };
globalThis.TripVisitDraft = { isDirty: () => false };
globalThis.TripBriefingForm = { populate() {}, payload: () => ({ participants: [] }) };
globalThis.TripBriefingPicker = { render() {}, markSelection() {} };

let release;
globalThis.ApiClient = {
  putTripBriefing: () => new Promise(resolve => { release = resolve; }),
  getTripPlan: async () => State.currentTripPlan,
};
TripBriefingDraft.load('stop-1', { participants: [] });
const saving = TripBriefingActions.save();
const duringSave = { editable: !content.disabled, canAddRow: !addRow.disabled };
content.value = 'typed while the request was out';
release({ participants: [] });
await saving;
console.log(JSON.stringify({ duringSave, kept: content.value }));
""", ("inquiry-edit-freeze.js", "trip-plan-identity.js", "trip-plan-refresh.js",
      "trip-briefing-reveal.js", "trip-briefing-draft.js",
      "trip-briefing-session.js", "trip-briefing-actions.js"))
    assert data["duringSave"]["editable"] is False, (
        "the form stayed editable while the save was in flight, so anything "
        "typed next was neither sent nor kept"
    )
    assert data["duringSave"]["canAddRow"] is False, (
        "rows could still be added and removed while the save was in flight"
    )


def check_an_older_save_does_not_close_the_editor_the_reader_opened() -> None:
    """A save that lands after the reader moved on keeps its hands off.

    Close this visit, choose another plan, start writing there - and the older
    answer closed *that* editor and pulled the screen back to the plan the
    reader had left. The write itself is real, so it is reported rather than
    hidden.
    """
    data = run("""
const editor = { hidden: false, innerHTML: '', querySelectorAll: () => [],
  closest: () => ({ classList: { toggle() {} } }), setAttribute() {},
  scrollIntoView() {} };
globalThis.document = {
  getElementById: id => (id === 'trip-briefing-editor' ? editor : null),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
};
const planA = { id: 'plan-a', planning_mode: 'team', members: [], stops: [{ id: 'stop-1' }] };
const planB = { id: 'plan-b', planning_mode: 'team', members: [], stops: [{ id: 'stop-2' }] };
globalThis.State = { currentTripPlan: planA };
globalThis.TripZones = { planChanged() {}, renderHeader() {}, current: () => 'briefing' };
globalThis.TripScheduleView = { renderPlan() {} };
globalThis.TripPlannerModule = { renderVisitExecution() {} };
globalThis.TripVisitDraft = { isDirty: () => false };
globalThis.TripBriefingForm = { populate() {}, payload: () => ({ participants: [] }) };
globalThis.TripBriefingPicker = { render() {}, markSelection() {} };
const reads = [];
let release;
globalThis.ApiClient = {
  putTripBriefing: () => new Promise(resolve => { release = resolve; }),
  getTripBriefing: async () => ({ participants: [] }),
  getTripPlan: async id => { reads.push(id); return id === 'plan-b' ? planB : planA; },
};

TripBriefingDraft.load('stop-1', { participants: [] });
const saving = TripBriefingActions.save();
// The reader closes this visit, moves to plan B and starts writing there.
TripBriefingActions.close({ force: true });
State.currentTripPlan = planB;
await TripBriefingActions.open('stop-2');
TripBriefingDraft.markDirty();
release({ participants: [] });
await saving;
console.log(JSON.stringify({
  plan: State.currentTripPlan.id,
  openStop: TripBriefingDraft.getStopId(),
  stillDirty: TripBriefingDraft.isDirty(),
  editorClosed: editor.hidden,
  reads, notes,
}));
""", ("inquiry-edit-freeze.js", "trip-plan-identity.js", "trip-plan-refresh.js",
      "trip-briefing-reveal.js", "trip-briefing-draft.js",
      "trip-briefing-session.js", "trip-briefing-actions.js"))
    assert data["plan"] == "plan-b", (
        f"the older save pulled the screen back to the plan the reader left: {data['plan']}"
    )
    assert data["openStop"] == "stop-2", (
        f"the older save cleared the draft the reader is writing: {data['openStop']}"
    )
    assert data["stillDirty"] is True, "the reader's unsaved work was marked clean"
    assert data["editorClosed"] is False, "the older save closed the new editor"
    assert "plan-a" not in data["reads"], (
        "the older save read its own plan back over the one on screen"
    )
    assert any("saved" in note.lower() for note in data["notes"]), (
        "the write happened and nobody was told, which reads as lost work"
    )

    # The reader can also leave by changing plans without touching this editor.
    moved = run("""
const editor = { hidden: false, innerHTML: '', querySelectorAll: () => [],
  closest: () => ({ classList: { toggle() {} } }), setAttribute() {},
  scrollIntoView() {} };
globalThis.document = {
  getElementById: id => (id === 'trip-briefing-editor' ? editor : null),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
};
const planA = { id: 'plan-a', planning_mode: 'team', members: [], stops: [{ id: 'stop-1' }] };
const planB = { id: 'plan-b', planning_mode: 'team', members: [], stops: [{ id: 'stop-1' }] };
globalThis.State = { currentTripPlan: planA };
globalThis.TripZones = { planChanged() {}, renderHeader() {}, current: () => 'briefing' };
globalThis.TripScheduleView = { renderPlan() {} };
globalThis.TripPlannerModule = { renderVisitExecution() {} };
globalThis.TripVisitDraft = { isDirty: () => false };
globalThis.TripBriefingForm = { populate() {}, payload: () => ({ participants: [] }) };
globalThis.TripBriefingPicker = { render() {}, markSelection() {} };
const reads = [];
let release;
globalThis.ApiClient = {
  putTripBriefing: () => new Promise(resolve => { release = resolve; }),
  getTripPlan: async id => { reads.push(id); return id === 'plan-b' ? planB : planA; },
};
TripBriefingDraft.load('stop-1', { participants: [] });
const saving = TripBriefingActions.save();
// Same stop id on both plans: only the plan tells them apart.
State.currentTripPlan = planB;
release({ participants: [] });
await saving;
console.log(JSON.stringify({ plan: State.currentTripPlan.id, reads }));
""", ("inquiry-edit-freeze.js", "trip-plan-identity.js", "trip-plan-refresh.js",
      "trip-briefing-reveal.js", "trip-briefing-draft.js",
      "trip-briefing-session.js", "trip-briefing-actions.js"))
    assert moved["plan"] == "plan-b" and "plan-a" not in moved["reads"], (
        "changing plans while a save was in flight let the older answer read "
        f"its own plan back over the one on screen: {moved}"
    )


def check_an_address_search_cannot_thaw_a_form_being_saved() -> None:
    """A search started before the save answers after the freeze.

    Its results are buttons that were not there to be held, and choosing one
    rebuilds the form - unfrozen - over the values the save already took. The
    new address was then neither sent nor kept.
    """
    data = run("""
const fields = [];
function field(id, value = '') {
  const node = { id, value, disabled: false, attributes: {},
    setAttribute(name) { this.attributes[name] = ''; },
    hasAttribute(name) { return name in this.attributes; },
    removeAttribute(name) { delete this.attributes[name]; },
    dataset: { locationField: id.replace('trip-briefing-location-', '') } };
  fields.push(node);
  return node;
}
const address = field('trip-briefing-location-address', 'Berlin');
const candidates = { id: 'trip-briefing-location-candidates', innerHTML: '' };
const status = { id: 'trip-briefing-location-status', textContent: '' };
const editor = { hidden: false, innerHTML: '', querySelectorAll: () => fields,
  closest: () => ({ classList: { toggle() {} } }), setAttribute() {},
  scrollIntoView() {} };
const byId = { 'trip-briefing-editor': editor,
  'trip-briefing-location-candidates': candidates,
  'trip-briefing-location-status': status };
globalThis.document = {
  getElementById: id => byId[id] || null,
  querySelector: () => null,
  querySelectorAll: selector => (selector.includes('data-location-field') ? [address] : []),
  addEventListener() {},
};
globalThis.State = { currentTripPlan: { id: 'plan-a', planning_mode: 'team',
  members: [], stops: [{ id: 'stop-1' }] } };
globalThis.TripZones = { planChanged() {}, renderHeader() {}, current: () => 'briefing' };
globalThis.TripScheduleView = { renderPlan() {} };
globalThis.TripPlannerModule = { renderVisitExecution() {} };
globalThis.TripVisitDraft = { isDirty: () => false };
let located = null;
globalThis.TripBriefingForm = { populate() {}, payload: () => ({ participants: [] }),
  setLocation: value => { located = value; } };
globalThis.TripBriefingPicker = { render() {}, markSelection() {} };
let releaseSearch, releaseSave;
globalThis.ApiClient = {
  searchGeocode: () => new Promise(resolve => { releaseSearch = resolve; }),
  putTripBriefing: () => new Promise(resolve => { releaseSave = resolve; }),
  getTripPlan: async () => State.currentTripPlan,
};
TripBriefingDraft.load('stop-1', { participants: [] });
const searching = TripBriefingGeocode.searchLocation();
const saving = TripBriefingActions.save();
const frozen = address.disabled;
releaseSearch({ candidates: [{ lat: 1, lng: 2, normalized_address: 'new address' }] });
await searching;
const afterSearch = { buttons: candidates.innerHTML.length, editable: !address.disabled };
releaseSave({ participants: [] });
await saving;
console.log(JSON.stringify({ frozen, afterSearch, located }));
""", ("inquiry-edit-freeze.js", "trip-plan-identity.js", "trip-plan-refresh.js",
      "trip-briefing-reveal.js", "trip-briefing-draft.js",
      "trip-briefing-session.js", "trip-briefing-actions.js",
      "trip-briefing-geocode.js"))
    assert data["frozen"] is True, "the form was not held while the save was in flight"
    assert data["afterSearch"]["buttons"] == 0, (
        "a late address search drew候选 buttons over a form being saved, and "
        "they were not held because they did not exist when the freeze happened"
    )
    assert data["afterSearch"]["editable"] is False, (
        "the form was editable again while its save was still in flight"
    )
    assert data["located"] is None, "a location was applied over a save in flight"


def check_a_failed_refresh_after_a_good_write_is_reported() -> None:
    """Written, then the screen could not be brought up to date.

    Both halves have to be said. Silence left the reader looking at the old
    summary with no idea whether the work was saved - and saying "failed"
    would send them to save it a second time.
    """
    data = run("""
const editor = { hidden: false, innerHTML: '', querySelectorAll: () => [],
  closest: () => ({ classList: { toggle() {} } }), setAttribute() {},
  scrollIntoView() {} };
globalThis.document = {
  getElementById: id => (id === 'trip-briefing-editor' ? editor : null),
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
};
globalThis.State = { currentTripPlan: { id: 'plan-a', planning_mode: 'team',
  members: [], stops: [{ id: 'stop-1' }] } };
globalThis.TripZones = { planChanged() {}, renderHeader() {}, current: () => 'briefing' };
globalThis.TripScheduleView = { renderPlan() {} };
globalThis.TripPlannerModule = { renderVisitExecution() {} };
globalThis.TripVisitDraft = { isDirty: () => false };
globalThis.TripBriefingForm = { populate() {}, payload: () => ({ participants: [] }) };
globalThis.TripBriefingPicker = { render() {}, markSelection() {} };
let writes = 0, reads = 0;
globalThis.ApiClient = {
  putTripBriefing: async () => { writes += 1; return { participants: [] }; },
  getTripPlan: async () => { reads += 1; throw new Error('network down'); },
};
TripBriefingDraft.load('stop-1', { participants: [] });
await TripBriefingActions.save();
console.log(JSON.stringify({ writes, reads, notes, closed: editor.hidden }));
""", ("inquiry-edit-freeze.js", "trip-plan-identity.js", "trip-plan-refresh.js",
      "trip-briefing-reveal.js", "trip-briefing-draft.js",
      "trip-briefing-session.js", "trip-briefing-actions.js"))
    assert data["writes"] == 1 and data["reads"] == 1, data
    assert data["notes"], (
        "the write succeeded, the re-read failed, and the reader was told "
        "nothing at all"
    )
    said = " ".join(data["notes"]).lower()
    assert "saved" in said and "refresh" in said, (
        f"the message does not say both halves - saved, not refreshed: {data['notes']}"
    )
    assert "do not save again" in said, (
        "nothing stops the reader saving a second time over a write that landed"
    )


def check_the_whole_team_stays_whoever_is_travelling() -> None:
    """A visit nobody edited still means "whoever is travelling".

    The team is filled in so the card does not read as "nobody is going".
    Writing that back would fix the list to those names, and a member who joins
    the trip afterwards would be left off the visit without a word.
    """
    data = run("""
globalThis.State = { currentTripPlan: { planning_mode: 'team', members: [
  { user_id: 'a', display_name: 'Ayden' }, { user_id: 'b', display_name: 'Slluu' },
] } };
globalThis.document = { getElementById: () => null, querySelector: () => null };
const draft = TripBriefingDraft;
const shown = draft.normalizeRecord({}).participants.map(row => row.user_id);
const untouched = draft.isWholeTeam(draft.normalizeRecord({}).participants);
const trimmed = draft.isWholeTeam([{ user_id: 'a' }]);
const noted = draft.isWholeTeam([
  { user_id: 'a', responsibility: 'demo' }, { user_id: 'b' },
]);
State.currentTripPlan = { planning_mode: 'legacy', members: [] };
const legacy = draft.isWholeTeam([{ user_id: 'a' }]);

// And the two sources are told apart, not guessed from the current list.
State.currentTripPlan = { planning_mode: 'team', members: [
  { user_id: 'a', display_name: 'Ayden' }, { user_id: 'b', display_name: 'Slluu' },
] };
const team = draft.normalizeRecord({}).participants;
draft.load('stop-inherited', { participants: [] });
const inheritedStays = draft.staysInherited(team);
draft.load('stop-chosen', { participants: [{ user_id: 'a' }, { user_id: 'b' }] });
const chosenStays = draft.staysInherited(team);
draft.load('stop-inherited', { participants: [] });
// Through the control the reader actually uses, not the flag underneath it.
globalThis.TripBriefingRows = { syncModel() {}, renderForm() {} };
globalThis.TripBriefingScroll = { replace() {}, focusRow() {}, keep() {} };
globalThis.TripBriefingReveal = { editor: () => null, open: () => null, show: () => null };
TripBriefingForm.populate({ participants: [] });
TripBriefingForm.arrayAction('participants', 'add');
const editedStays = draft.staysInherited(team);
console.log(JSON.stringify({ shown, untouched, trimmed, noted, legacy,
  inheritedStays, chosenStays, editedStays }));
""", ("trip-briefing-draft.js", "trip-briefing-form.js"))
    assert data["shown"] == ["a", "b"], (
        f"the card must read as the whole team, not as nobody: {data['shown']}"
    )
    assert data["untouched"] is True, (
        "a list nobody changed still means whoever is travelling, so the visit "
        "keeps including members who join the trip later"
    )
    assert data["trimmed"] is False, (
        "taking somebody off makes the list a decision about who goes"
    )
    assert data["noted"] is False, (
        "anything typed against a person is a decision about that person"
    )
    assert data["legacy"] is False, "a single-traveller plan has no team to inherit"

    # A chosen list that happens to equal the team is still a chosen list.
    assert data["inheritedStays"] is True, (
        "a visit that named nobody stopped meaning whoever is travelling"
    )
    assert data["chosenStays"] is False, (
        "a list the reader chose was turned back into inheritance because it "
        "happened to match the team - a colleague joining later would be added "
        "to a visit nobody put them on"
    )
    assert data["editedStays"] is False, (
        "the reader edited the people and the list still went back as inherited"
    )

    saving = (MODULES / "trip-briefing-actions.js").read_text(encoding="utf-8")
    assert "TripBriefingDraft.staysInherited(payload.participants)" in saving, (
        "the save has to send the inherited list back as inherited"
    )


def check_a_half_written_visit_card_survives_a_refresh() -> None:
    """Re-reading the plan does not wipe a card somebody is writing in.

    The visit execution cards are typed into directly, and redrawing rebuilds
    them from the server. Saving a visit's preparation re-reads the plan, and
    that redraw took the unsaved result card with it.
    """
    data = run("""
globalThis.State = { currentTripPlan: { id: 'p1' } };
globalThis.document = { getElementById: () => null };
globalThis.ApiClient = { getTripPlan: async id => ({ id, stops: [], members: [] }) };
let redraws = 0;
globalThis.TripPlannerModule = { renderVisitExecution: () => { redraws += 1; } };
globalThis.TripScheduleView = { renderPlan: () => {} };

// Somebody is part way through a result card.
globalThis.TripVisitDraft = { isDirty: () => true };
await TripPlanRefresh.reread('p1');
const whileWriting = redraws;

// Nothing unsaved: the cards are rebuilt as before.
globalThis.TripVisitDraft = { isDirty: () => false };
await TripPlanRefresh.reread('p1');
console.log(JSON.stringify({ whileWriting, afterwards: redraws }));
""", ("trip-plan-identity.js", "trip-plan-refresh.js"))
    assert data["whileWriting"] == 0, (
        "a card being written in must not be rebuilt from the server: what was "
        "typed into it is gone and nothing says so"
    )
    assert data["afterwards"] == 1, (
        "with nothing unsaved the cards must still be brought up to date"
    )

    # Every place the redraw is only a side effect goes through the same rule.
    for name in ("trip-plan-refresh.js", "trip-stop-appointment-actions.js"):
        source = (MODULES / name).read_text(encoding="utf-8")
        assert "renderVisitExecution(State.currentTripPlan)" not in source, (
            f"{name} redraws the cards without checking for unsaved work in them"
        )


def check_a_late_member_answer_does_not_drag_the_reader_back() -> None:
    """An answer that arrives after the reader moved on is dropped.

    A member save on a slow connection answers with the plan it changed. Taking
    it as the current plan puts the reader back on the trip they just left.
    """
    data = run("""
globalThis.document = { getElementById: () => null };
globalThis.State = { currentTripPlan: { id: 'A', title: 'Plan A', members: [
  { user_id: 'a', display_name: 'Ayden', departure_date: '2026-09-13', row_version: 1 },
] } };
globalThis.ApiClient = { setTripMember: async () => {
  // While this is in flight, the reader opens another plan - which claims the
  // screen the same way every other plan-changing action does.
  TripPlanIdentity.accept(TripPlanIdentity.intend(),
    { id: 'B', title: 'Plan B', members: [] });
  return { id: 'A', title: 'Plan A', members: [] };
} };
await TripTeamActions.departureChanged('a', '2026-09-20');
console.log(JSON.stringify({ showing: State.currentTripPlan.id, notes }));
""", ("trip-plan-identity.js", "trip-team-queue.js",
         "trip-team-actions.js"))
    assert data["showing"] == "B", (
        "the answer belonged to the plan the reader left, and taking it put "
        f"them back on it: showing {data['showing']}"
    )


def check_renaming_leaves_a_saved_route_saved() -> None:
    """A rename does not make a saved route look unsaved.

    The name saves on its own, so the route is exactly as saved as it was a
    moment before. Marking the draft unsaved refuses the export and asks for a
    route nobody altered to be calculated again.
    """
    data = run("""
const field = { value: 'Trip October' };
globalThis.document = { getElementById: () => field, querySelectorAll: () => [] };
globalThis.State = { currentTripPlan: { id: 'p1', title: 'Trip Sept',
  row_version: 4, stops: [], legs: [] } };
globalThis.TripRouteValues = { transportPriority: () => ['flight'],
  cleanLegOverride: value => value };
globalThis.TripDuration = { readStopDuration: () => 2, normalizeHalfDays: v => v };
globalThis.TripTransportView = { render: () => {} };
globalThis.TripSuggestionState = { resetForPlan: () => {} };
globalThis.TripLegOverrides = { fromPlan: () => ({}) };
globalThis.TripPlanIdentity = {
  intend: () => 1,
  accept: (token, plan) => { State.currentTripPlan = plan; return true; },
};
__DRAFT__
TripPlanningDraft.hydrate(State.currentTripPlan, { committed: true });
const before = TripPlanningDraft.get().dirty;
globalThis.ApiClient = { updateTripPlan: async (id, body) =>
  ({ ...State.currentTripPlan, title: body.title, row_version: 5 }) };
await TripPlanTitleActions.titleChanged();
console.log(JSON.stringify({
  before, after: TripPlanningDraft.get().dirty,
  title: TripPlanningDraft.get().header.title,
}));
""".replace("__DRAFT__", (MODULES / "trip-planning-draft.js").read_text(
        encoding="utf-8")),
        ("trip-plan-title-actions.js",))
    assert data["before"] is False, "the route started out saved"
    assert data["after"] is False, (
        "renaming marked the saved route as unsaved, which refuses the export "
        "and asks for a route nobody altered to be calculated again"
    )
    assert data["title"] == "Trip October", (
        f"the draft still has to learn the new name: {data['title']}"
    )


def check_a_late_answer_never_reopens_the_plan_the_reader_left() -> None:
    """Answers that arrive after the reader moved on are dropped, everywhere.

    Requests the planner-wide busy state does not cover leave the reader free
    to open another plan while one is in flight. Taking the answer then puts
    them back on the trip they just left, with nothing on screen saying why.
    """
    data = run("""
globalThis.State = { currentTripPlan: { id: 'A' } };
globalThis.document = { getElementById: () => null };
globalThis.TripVisitDraft = { isDirty: () => false };
globalThis.TripPlannerModule = { renderVisitExecution: () => { drew.push('visits'); } };
globalThis.TripScheduleView = { renderPlan: () => { drew.push('schedule'); } };
globalThis.renderTripMap = () => { drew.push('map'); };
globalThis.renderCurrentTripPlan = () => { drew.push('cards'); };
const drew = [];
globalThis.ApiClient = { getTripPlan: async id => {
  // While the read is in flight the reader opens another plan.
  TripPlanIdentity.accept(TripPlanIdentity.intend(), { id: 'B' });
  return { id, title: 'Plan A', stops: [], members: [] };
} };
const late = await TripPlanRefresh.reread('A');
const afterLate = { showing: State.currentTripPlan.id, drew: [...drew] };

// The ordinary case still works.
drew.length = 0;
globalThis.ApiClient = { getTripPlan: async id =>
  ({ id, title: 'Plan B', stops: [], members: [] }) };
const ok = await TripPlanRefresh.reread('B');
console.log(JSON.stringify({ late, afterLate, ok,
  title: State.currentTripPlan.title, drew }));
""", ("trip-plan-identity.js", "trip-plan-refresh.js"))
    assert data["late"] is False, (
        "a re-read whose answer arrived after the reader moved on must report "
        "that it did not happen"
    )
    assert data["afterLate"]["showing"] == "B", (
        "the late answer pulled the reader back to the plan they left: "
        f"{data['afterLate']['showing']}"
    )
    assert data["afterLate"]["drew"] == [], (
        f"nothing may be redrawn from a discarded answer: {data['afterLate']['drew']}"
    )
    assert data["ok"] is True and data["title"] == "Plan B", data
    assert "map" in data["drew"], "the ordinary case still redraws everything"


def check_nothing_writes_the_current_plan_behind_the_rule() -> None:
    """Every module that changes the plan on screen goes through one rule.

    Deciding which writes could be raced by reading each one is how the create
    and the background reload were missed: both looked covered and were not. So
    the whole frontend is scanned instead. One module owns the write, everything
    else asks it, and a module added later cannot quietly opt out.
    """
    import re

    owner = "trip-plan-identity.js"
    offenders = []
    for path in sorted(ROOT.joinpath("frontend", "js").rglob("*.js")):
        if path.name == owner:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"\bState\.currentTripPlan\s*=", line):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, (
        "these write the plan on screen directly, so an answer that arrives "
        f"after the reader moved on can still win: {offenders}"
    )

    rule = (MODULES / owner).read_text(encoding="utf-8")
    for needed in ("function intend(", "function accept(", "function clear("):
        assert needed in rule, f"{owner} no longer offers {needed}"

    # Taking a number and never checking it would pass the scan above while
    # letting every late answer through, so the two have to appear together.
    for path in sorted(MODULES.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        if "TripPlanIdentity.intend()" not in source:
            continue
        assert ("TripPlanIdentity.accept(" in source
                or "TripPlanIdentity.clear(" in source
                or "TripPlanIdentity.isCurrent(" in source), (
            f"{path.name} claims the screen and never checks it still has it"
        )


def check_an_old_action_cannot_outrank_a_newer_choice() -> None:
    """Finishing an old action does not overrule what the reader chose since.

    Archiving reloads the planner when it is done. The reload took a number of
    its own, which was newer than the one the reader's next choice had taken -
    so the tail of the archive won, and the plan they had just opened was
    replaced by whatever the reload happened to select.
    """
    data = run("""
globalThis.State = { currentTripPlan: { id: 'C' }, tripPlans: [], tripBusy: false,
  tripCandidatePagination: { offset: 0, limit: 25 } };
globalThis.document = { getElementById: () => null };
globalThis.confirm = () => true;
globalThis.alert = () => {};
globalThis.escapeHtml = value => String(value ?? '');
globalThis.formatDate = value => value;
globalThis.populateTripPlanForm = () => {};
globalThis.renderCurrentTripPlan = () => {};
globalThis.renderTripMap = () => {};
globalThis.readTripPlanFormPayload = () => ({});
globalThis.setTripBusy = () => {};
globalThis.handleTripError = async () => {};
globalThis.syncTripPlanListEntry = () => {};
globalThis.TripPlanningDraft = { get: () => ({ dirty: false }), change: () => {} };
globalThis.TripVisitDraft = { reset: () => {}, guard: () => false };
globalThis.TripBriefingDraft = { guard: () => false };
globalThis.TripFreeStopDraft = { isDirty: () => false };

let releaseArchive;
const archived = new Promise(done => { releaseArchive = done; });
globalThis.ApiClient = {
  archiveTripPlan: async () => archived,
  getTripPlan: async id => ({ id }),
};
// The reload that follows an archive: it must not claim the screen for itself.
globalThis.loadTripPlanner = async (options = {}) => {
  const token = options.token ?? TripPlanIdentity.intend();
  if (!TripPlanIdentity.isCurrent(token)) return false;
  TripPlanIdentity.accept(token, { id: 'C' });
  return true;
};

// Looking at C, the reader archives A, then opens B before A answers.
const archiving = archiveTripPlan('A', 1);
const opening = selectTripPlan('B');
await opening;
releaseArchive();
await archiving;
console.log(JSON.stringify({ showing: State.currentTripPlan?.id }));
""", ("trip-plan-identity.js", "trip-plans.js"))
    assert data["showing"] == "B", (
        "the reader opened B, and the tail of the archive they started earlier "
        f"put them somewhere else: showing {data['showing']}"
    )


def check_a_follow_up_reload_never_claims_a_newer_number() -> None:
    """A reload finishing somebody else's action carries that action's number.

    Taking a fresh one makes the end of an old action newer than everything the
    reader has done since, which is exactly how an archive could beat the plan
    they opened while it ran.
    """
    import re

    loader = (MODULES / "trip-loader.js").read_text(encoding="utf-8")
    assert "options.token ?? TripPlanIdentity.intend()" in loader, (
        "the planner reload must use the number of whatever asked for it, and "
        "only take one of its own when nothing did"
    )
    assert "if (!TripPlanIdentity.isCurrent(token)) return false;" in loader, (
        "a reload for an action the reader has moved past must not run"
    )

    # Anything holding a number passes it on rather than letting the reload
    # take a newer one.
    for path in sorted(MODULES.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        if "TripPlanIdentity.intend()" not in source:
            continue
        bare = re.findall(r"loadTripPlanner\(\s*\)", source)
        assert not bare, (
            f"{path.name} holds a number and then lets the reload take a newer "
            "one, so the end of its own action outranks whatever the reader "
            "chose while it ran"
        )

    # A number taken only when one was not handed in is safe exactly when it is
    # taken before the function waits for anything: taken later, it would be
    # newer than whatever the reader did while the request was in flight, and
    # the tail of the old action would win. So the rule is about where it is
    # taken, and that is what is checked.
    for path in sorted(MODULES.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for position in _positions(source, "?? TripPlanIdentity.intend()"):
            opening = max(
                source.rfind(keyword, 0, position)
                for keyword in ("function ", "=> {")
            )
            assert "await" not in source[opening:position], (
                f"{path.name} takes a number only when one was not handed to "
                "it, and does so after already waiting for something, so it "
                "can end up newer than what the reader chose meanwhile"
            )


def _positions(source: str, needle: str) -> list[int]:
    found, start = [], source.find(needle)
    while start != -1:
        found.append(start)
        start = source.find(needle, start + 1)
    return found


def check_browsing_candidates_does_not_cancel_a_plan_switch() -> None:
    """Paging the customer list is not a reason to change which plan is open.

    Loading more candidates went through the whole planner reload, which claims
    the screen and reloads whichever plan it finds. Scrolling the list while a
    plan was opening therefore put the reader back on the previous plan, with
    nothing said.
    """
    data = run("""
globalThis.State = { currentTripPlan: { id: 'C' }, tripPlans: [{ id: 'C' }],
  tripCandidates: [{ id: 'one' }],
  tripCandidatePagination: { offset: 0, limit: 25 }, tripBusy: false };
globalThis.document = { getElementById: () => null };
globalThis.escapeHtml = value => String(value ?? '');
globalThis.getTripFilters = () => ({});
globalThis.initTripPlannerMap = () => {};
globalThis.setPanelLoading = () => {};
globalThis.setPanelError = () => {};
globalThis.renderTripCandidates = () => { drew.push('candidates'); };
globalThis.renderTripMap = () => {};
globalThis.renderTripPlans = () => {};
globalThis.renderCurrentTripPlan = () => {};
globalThis.populateTripPlanForm = () => {};
globalThis.syncTripPlanListEntry = () => {};
globalThis.TripVisitDraft = { reset: () => {}, guard: () => false };
globalThis.TripBriefingDraft = { guard: () => false };
globalThis.TripFreeStopDraft = { isDirty: () => false };
globalThis.TripPlanningDraft = { get: () => ({ dirty: false }), hydrate: () => {} };
const drew = [];

let releaseB;
const openingB = new Promise(done => { releaseB = done; });
globalThis.ApiClient = {
  getTripPlan: async id => (id === 'B' ? openingB.then(() => ({ id })) : { id }),
  listTripPlans: async () => [{ id: 'C' }],
  getTripCandidates: async () => ({ candidates: [{ id: 'two' }],
    pagination: { offset: 25, limit: 25 } }),
};

// The reader opens B; while it is still opening they scroll the customer list.
const switching = selectTripPlan('B');
await loadTripCandidates({ append: true });
const whileOpening = State.currentTripPlan?.id;
releaseB();
await switching;
console.log(JSON.stringify({
  whileOpening, showing: State.currentTripPlan?.id,
  candidates: State.tripCandidates.length, drew,
}));
""", ("trip-plan-identity.js", "trip-candidate-requests.js",
        "trip-loader.js", "trip-plans.js"))
    assert data["showing"] == "B", (
        "the reader opened B and then scrolled the customer list, which put "
        f"them back on the plan they left: showing {data['showing']}"
    )
    assert data["whileOpening"] == "C", (
        "paging the list must not change which plan is open before the switch "
        f"it was waiting on has answered: {data['whileOpening']}"
    )
    assert data["candidates"] == 2, (
        f"the next page of customers still has to arrive: {data['candidates']}"
    )
    assert "candidates" in data["drew"], "and the list still has to be redrawn"

    source = (MODULES / "trip-candidates-list.js").read_text(encoding="utf-8")
    paging = source[source.index("window.loadMoreTripCandidates"):]
    assert "loadTripCandidates(" in paging and "loadTripPlanner" not in paging, (
        "paging the customer list must not go through the planner reload"
    )
    loader = (MODULES / "trip-loader.js").read_text(encoding="utf-8")
    reset = loader[:loader.index("window.loadTripCandidates")]
    assert "loadTripCandidates({ append: false, offset: 0 })" in reset, (
        "clearing the customer filters is the same concern as paging them, and "
        "must not reload the plan either"
    )
    assert "loadTripPlanner" not in reset, (
        "clearing the filters must not go through the planner reload"
    )
    candidates = loader[loader.index("window.loadTripCandidates"):
                        loader.index("window.loadTripPlanner")]
    for forbidden in ("TripPlanIdentity", "currentTripPlan", "listTripPlans"):
        assert forbidden not in candidates, (
            f"loading candidates must not touch {forbidden}: it is a list of "
            "customers, not a decision about which plan is on screen"
        )


CANDIDATE_HARNESS = """
globalThis.State = { tripCandidates: [{ id: 'base' }], currentTripPlan: null,
  tripCandidatePagination: { offset: 0, limit: 25, has_more: true } };
let region = 'EU';
globalThis.setRegion = value => { region = value; };
globalThis.getTripFilters = () => ({ region, sales_stage: '',
  limit: State.tripCandidatePagination.limit,
  offset: State.tripCandidatePagination.offset });
globalThis.initTripPlannerMap = () => {};
globalThis.setPanelLoading = () => {};
globalThis.setPanelError = () => { errors += 1; };
globalThis.renderTripCandidates = () => {};
globalThis.renderTripMap = () => {};
globalThis.document = { getElementById: () => null };
globalThis.errors = 0;
globalThis.notices = [];
globalThis.notify = message => notices.push(message);
globalThis.I18n = { t: value => value };
"""


def run_candidates(body: str) -> dict:
    return run(CANDIDATE_HARNESS + body,
               ("trip-candidate-requests.js", "trip-loader.js",
                "trip-candidates-list.js"))


def check_an_answer_to_an_old_filter_is_not_mixed_in() -> None:
    """Customers found under one filter do not join the list of another.

    Paging is a round trip. Change the filter while page two is on its way and
    it arrives describing customers the reader is no longer asking about; put
    into the list it sits next to results of a different question, and nothing
    on screen says which is which.
    """
    data = run_candidates("""
let releaseOld;
const oldPage = new Promise(done => { releaseOld = done; });
let call = 0;
globalThis.ApiClient = { getTripCandidates: async filters => {
  call += 1;
  if (call === 1) return oldPage.then(() => ({
    candidates: [{ id: 'old-page-2' }],
    pagination: { offset: 25, limit: 25, has_more: false },
  }));
  return { candidates: [{ id: 'new-base' }],
           pagination: { offset: 0, limit: 25, has_more: true } };
} };

// Page two of Europe is still on its way when the reader switches to America.
const paging = loadMoreTripCandidates();
setRegion('NA');
await resetTripPlannerFilters();
const afterReset = State.tripCandidates.map(item => item.id);
releaseOld();
await paging;
console.log(JSON.stringify({ afterReset,
  afterOldArrives: State.tripCandidates.map(item => item.id),
  offset: State.tripCandidatePagination.offset }));
""")
    assert data["afterReset"] == ["new-base"], data["afterReset"]
    assert data["afterOldArrives"] == ["new-base"], (
        "customers found under the previous filter were added to the list of "
        f"the new one: {data['afterOldArrives']}"
    )
    assert data["offset"] == 0, (
        f"the stale answer also moved the page marker: {data['offset']}"
    )

    # Only the newest request may write, which holds because every way of
    # changing the question starts one. A filter that changed the list without
    # starting a request would leave the previous answer looking newest.
    import re

    filters = _source("frontend/js/modules/trip-form.js")
    asked = set(re.findall(r"getElementById\('([\w-]+)'\)", filters[
        filters.index("function getTripFilters"):filters.index("\n}", filters.index(
            "function getTripFilters"))]))
    bindings = _source("frontend/js/modules/stage-filters.js")
    for control in sorted(asked):
        assert re.search(
            rf"bindOnce\('{re.escape(control)}',\s*'change',\s*window\.resetTripPlannerFilters",
            bindings,
        ), (
            f"{control} is part of what the customer list is filtered by, but "
            "changing it does not start a fresh request - so an answer to the "
            "previous filter would still be the newest one and would be shown"
        )


def check_pages_cannot_arrive_out_of_order() -> None:
    """Two pages are never in flight together.

    Clicked twice, the second page can answer before the first. Appended in
    that order the list reads backwards, and the page marker ends up describing
    whichever answer happened to land last - so the next click fetches a page
    the list already holds.
    """
    data = run_candidates("""
let calls = [];
globalThis.ApiClient = { getTripCandidates: async filters => {
  calls.push(filters.offset);
  // The later page answers first, if it is allowed to be asked for at all.
  await new Promise(done => setTimeout(done, filters.offset === 25 ? 20 : 1));
  return { candidates: [{ id: `page-${filters.offset}` }],
           pagination: { offset: filters.offset, limit: 25, has_more: true } };
} };
await Promise.all([loadMoreTripCandidates(), loadMoreTripCandidates()]);
const bothClicks = [...calls];
const afterBoth = State.tripCandidates.map(item => item.id);
await loadMoreTripCandidates();
console.log(JSON.stringify({ calls: bothClicks, afterBoth,
  afterNext: State.tripCandidates.map(item => item.id),
  offset: State.tripCandidatePagination.offset }));
""")
    assert data["calls"] == [25], (
        f"only one page may be asked for at a time: {data['calls']}"
    )
    assert data["afterBoth"] == ["base", "page-25"], data["afterBoth"]
    assert data["afterNext"] == ["base", "page-25", "page-50"], (
        f"the next click must fetch the page after the one held: {data['afterNext']}"
    )
    assert len(set(data["afterNext"])) == len(data["afterNext"]), (
        f"no customer may appear twice: {data['afterNext']}"
    )


def check_a_page_that_failed_is_the_page_asked_for_again() -> None:
    """A page that did not arrive is not skipped.

    The marker used to move before the request was made, so a page that failed
    left the reader on the next one - and the customers on the failed page were
    unreachable without clearing the filters.
    """
    data = run_candidates("""
let attempts = [];
let failNext = true;
globalThis.ApiClient = { getTripCandidates: async filters => {
  attempts.push(filters.offset);
  if (failNext) { failNext = false; throw new Error('network'); }
  return { candidates: [{ id: `page-${filters.offset}` }],
           pagination: { offset: filters.offset, limit: 25, has_more: true } };
} };
await loadMoreTripCandidates();
const afterFailure = State.tripCandidatePagination.offset;
await loadMoreTripCandidates();
console.log(JSON.stringify({ attempts, afterFailure,
  list: State.tripCandidates.map(item => item.id),
  offset: State.tripCandidatePagination.offset, notices }));
""")
    assert data["attempts"] == [25, 25], (
        f"the page that failed has to be the one asked for again: {data['attempts']}"
    )
    assert data["afterFailure"] == 0, (
        f"a page that never arrived must not move the marker: {data['afterFailure']}"
    )
    assert data["list"] == ["base", "page-25"], data["list"]
    assert data["notices"], "the reader has to be told the page did not arrive"


def check_an_old_page_does_not_block_the_list_being_read() -> None:
    """A page still arriving for a filter nobody is looking at blocks nothing.

    One page at a time is right among requests for the same question. Held
    across all of them, a slow page for an abandoned filter leaves the reader
    clicking Load more on the list in front of them with nothing happening and
    nothing said - until the old request they cannot see finally answers.
    """
    data = run_candidates("""
let releaseOld;
const oldPage = new Promise(done => { releaseOld = done; });
const asked = [];
globalThis.ApiClient = { getTripCandidates: async filters => {
  asked.push(`${region}:${filters.offset}`);
  if (region === 'EU' && filters.offset === 25) {
    return oldPage.then(() => ({ candidates: [{ id: 'eu-page-2' }],
      pagination: { offset: 25, limit: 25, has_more: false } }));
  }
  return { candidates: [{ id: `na-${filters.offset}` }],
           pagination: { offset: filters.offset, limit: 25, has_more: true } };
} };

// Europe page two is on its way when the reader switches to America.
const stuck = loadMoreTripCandidates();
setRegion('NA');
await resetTripPlannerFilters();
// America's first page is in. They ask for its second while Europe is stuck.
await loadMoreTripCandidates();
const whileStuck = { asked: [...asked],
  list: State.tripCandidates.map(item => item.id) };
releaseOld();
await stuck;
console.log(JSON.stringify({ whileStuck,
  afterOldArrives: State.tripCandidates.map(item => item.id) }));
""")
    assert "NA:25" in data["whileStuck"]["asked"], (
        "the reader asked for the next page of the list in front of them and "
        f"nothing was requested: {data['whileStuck']['asked']}"
    )
    assert data["whileStuck"]["list"] == ["na-0", "na-25"], (
        f"both pages of the list being read must be there: {data['whileStuck']['list']}"
    )
    assert data["afterOldArrives"] == ["na-0", "na-25"], (
        "the abandoned page arrived and was added to a list it does not belong "
        f"to: {data['afterOldArrives']}"
    )


def check_an_old_page_does_not_free_the_lock_somebody_else_holds() -> None:
    """Only the request holding the lock may give it up.

    Clearing the lock whenever anything finishes lets a late arrival open the
    door for a second page of the current list, and the two then answer in
    whatever order they please.
    """
    data = run_candidates("""
let releaseOld, releaseCurrent;
const oldPage = new Promise(done => { releaseOld = done; });
const currentPage = new Promise(done => { releaseCurrent = done; });
const asked = [];
globalThis.ApiClient = { getTripCandidates: async filters => {
  asked.push(`${region}:${filters.offset}`);
  if (region === 'EU') return oldPage.then(() => ({ candidates: [],
    pagination: { offset: 25, limit: 25, has_more: false } }));
  if (filters.offset === 25) return currentPage.then(() => ({
    candidates: [{ id: 'na-25' }],
    pagination: { offset: 25, limit: 25, has_more: true } }));
  return { candidates: [{ id: 'na-0' }],
           pagination: { offset: 0, limit: 25, has_more: true } };
} };

const stuck = loadMoreTripCandidates();
setRegion('NA');
await resetTripPlannerFilters();
const paging = loadMoreTripCandidates();      // NA page two, still loading
releaseOld();
await stuck;                                   // the old one finishes
// Must find the lock still held by the page that is genuinely loading, so it
// asks for nothing. Not awaited: if it wrongly starts one, that request is
// still in flight and the count below is what shows it.
const third = loadMoreTripCandidates();
await Promise.resolve();
const afterOldFinished = [...asked];
releaseCurrent();
await Promise.all([paging, third]);
console.log(JSON.stringify({ afterOldFinished, asked }));
""")
    assert data["afterOldFinished"].count("NA:25") == 1, (
        "an old request finishing let a second page of the current list start, "
        f"so two are in flight together: {data['afterOldFinished']}"
    )
    assert data["asked"].count("NA:25") == 1, data["asked"]


def main() -> None:
    check_a_failed_rename_puts_the_name_back()
    check_renaming_keeps_the_rest_of_the_route_draft()
    check_an_empty_name_is_refused_out_loud()
    check_member_dates_are_saved_one_at_a_time()
    check_a_failed_member_date_stops_claiming_it_saved()
    check_saving_a_visit_refreshes_even_while_another_editor_is_open()
    check_a_save_holds_the_form_it_took_its_values_from()
    check_an_older_save_does_not_close_the_editor_the_reader_opened()
    check_an_address_search_cannot_thaw_a_form_being_saved()
    check_a_failed_refresh_after_a_good_write_is_reported()
    check_the_whole_team_stays_whoever_is_travelling()
    check_a_half_written_visit_card_survives_a_refresh()
    check_a_late_member_answer_does_not_drag_the_reader_back()
    check_renaming_leaves_a_saved_route_saved()
    check_a_late_answer_never_reopens_the_plan_the_reader_left()
    check_nothing_writes_the_current_plan_behind_the_rule()
    check_an_old_action_cannot_outrank_a_newer_choice()
    check_a_follow_up_reload_never_claims_a_newer_number()
    check_browsing_candidates_does_not_cancel_a_plan_switch()
    check_an_answer_to_an_old_filter_is_not_mixed_in()
    check_pages_cannot_arrive_out_of_order()
    check_a_page_that_failed_is_the_page_asked_for_again()
    check_an_old_page_does_not_block_the_list_being_read()
    check_an_old_page_does_not_free_the_lock_somebody_else_holds()
    print("PASS: failed saves, racing saves and blocked refreshes")


if __name__ == "__main__":
    main()
