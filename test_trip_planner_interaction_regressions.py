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
globalThis.ApiClient = { setTripMember: async (planId, body) => {
  inFlight += 1;
  if (inFlight > 1) overlapped = true;
  // The first call answers slowly, the second quickly.
  await new Promise(done => setTimeout(done, body.user_id === 'a' ? 30 : 1));
  inFlight -= 1;
  order.push(body.user_id);
  return { ...State.currentTripPlan, members: State.currentTripPlan.members.map(
    member => member.user_id === body.user_id
      ? { ...member, departure_date: body.departure_date, row_version: 3 } : member) };
} };
await Promise.all([
  TripTeamActions.departureChanged('a', '2026-09-20'),
  TripTeamActions.departureChanged('b', '2026-09-21'),
]);
console.log(JSON.stringify({ order, overlapped,
  dates: State.currentTripPlan.members.map(m => m.departure_date) }));
""", ("trip-plan-identity.js", "trip-team-queue.js",
         "trip-team-actions.js"))
    assert data["overlapped"] is False, (
        "two member saves must not be in flight together, or the slower answer "
        "lands last and undoes the newer change"
    )
    assert data["order"] == ["a", "b"], (
        f"the saves must be answered in the order they were made: {data['order']}"
    )
    assert data["dates"] == ["2026-09-20", "2026-09-21"], (
        f"both changes must survive: {data['dates']}"
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
    assert "TripPlanRefresh.reread(planId)" in source, (
        "the plan has to be read back on its own after a visit is saved"
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
console.log(JSON.stringify({ shown, untouched, trimmed, noted, legacy }));
""", ("trip-briefing-draft.js",))
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

    saving = (MODULES / "trip-briefing-actions.js").read_text(encoding="utf-8")
    assert "TripBriefingDraft.isWholeTeam(payload.participants)" in saving, (
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
