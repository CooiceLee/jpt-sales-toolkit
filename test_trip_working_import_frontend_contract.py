"""Static contract checks for the field-workbook import panel."""

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent

# Every state the comparison can be in has to reach the reader as a sentence,
# never as the name the comparison uses for it internally.
INTERNAL_STATES = ("workbook_only", "current_only", "both_same", "unchanged")


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def check_the_panel_is_wired() -> None:
    index = _source("frontend/index.html")
    api = _source("frontend/js/api-client.js")
    module = _source("frontend/js/modules/trip-working-import.js")
    view = _source("frontend/js/modules/trip-working-import-view.js")
    helpers = ("trip-working-import-text.js", "trip-working-import-view.js",
               "trip-working-import-refresh.js")
    for value in (
        'id="trip-working-import-file"',
        'id="trip-working-preflight-btn"',
        'id="trip-working-commit-btn"',
        "trip-working-import.js", *helpers,
    ):
        assert value in index, value
    # Every helper loads before the panel that calls it.
    for helper in helpers:
        assert index.index(helper) < index.index("trip-working-import.js?"), helper
    for value in ("preflightTripWorking", "importTripWorking",
                  "/review/trip-working/preflight", "/review/trip-working/import",
                  "resolutions_json", "expected_preview_digest"):
        assert value in api, value
    for value in ("baseline", "uploaded", "current", "trip-working-conflict"):
        assert value in view, value
    assert "TripWorkingImportRefresh.after" in module

    # The file cannot be swapped under a request, and a stale answer cannot
    # land on the file that replaced it.
    assert "chooser.disabled = state.busy" in module, (
        "another file can be chosen while a request is still running"
    )
    # Both requests are numbered, and both drop an answer that is no longer
    # about the file on screen.
    assert module.count("const turn = ++state.turn") == 2, (
        "one of preflight and import does not number its request"
    )
    # Both the answer and the failure of each request are checked, so neither
    # can land on a file that has since been replaced.
    for name in ("preflight", "commit"):
        body = module[module.index(f"async function {name}("):]
        body = body[:body.index("\n    }")]
        assert body.count("if (turn !== state.turn) return") == 2, (
            f"{name} lets an abandoned request's answer or failure through: "
            f"{body.count('if (turn !== state.turn) return')}"
        )


def check_the_choice_is_carried_with_the_preview_it_was_made_on() -> None:
    """A choice is only valid against the values it was shown, so both travel."""
    module = _source("frontend/js/modules/trip-working-import.js")
    call = module[module.index("ApiClient.importTripWorking("):]
    call = call[:call.index(");")]
    assert "preview_digest" in call, (
        f"the panel submits without saying which preview the choices belong "
        f"to: {' '.join(call.split())}"
    )
    assert "report.resolutions_cleared" in module, (
        "a preview the server rejected leaves the old choices standing"
    )
    assert "state.resolutions = {}" in module
    # The plan the reader was on is noted before the request, not read back
    # afterwards when they may have opened another one.
    body = module[module.index("async function commit("):]
    body = body[:body.index("ApiClient.importTripWorking(")]
    assert "TripPlanIdentity.accepted()" in body, (
        "the import notes the newest plan asked for rather than the one on "
        "screen, so it can borrow the identity of a plan still loading"
    )
    assert "TripWorkingImportRefresh.after(report, tr, planTurn)" in module, (
        "the refresh is not told which plan the reader was on"
    )
    # A mixture of choices the server says cannot be saved is refused here.
    buttons = module[module.index("function syncButtons("):]
    buttons = buttons[:buttons.index("\n    }")]
    assert "TripWorkingImportView.unsaveable" in buttons, (
        "a mixture of choices that cannot be saved can still be submitted"
    )
    assert "|| unsaveable" in buttons, buttons
    assert "state.report.status === 'completed'" in module, (
        "the same results can be submitted twice by clicking again"
    )
    api = _source("frontend/js/api-client.js")
    conflict = api[api.index("class ConflictError"):api.index("// ===== Auth API")]
    assert "this.details = detail" in conflict, (
        "a 409 arrives with the new comparison to choose from and it is dropped"
    )


def check_nothing_internal_reaches_the_reader() -> None:
    module = _source("frontend/js/modules/trip-working-import.js")
    view = _source("frontend/js/modules/trip-working-import-view.js")
    text = _source("frontend/js/modules/trip-working-import-text.js")
    i18n = _source("frontend/js/i18n.js")
    module = module + view

    # Comparing against a state name is logic; printing one is not. The state
    # only reaches the page through the table that gives it a sentence.
    # Whether a sample or a quote is needed is an answer, not a machine value.
    assert "if (item === true) return esc(tr('Yes'));" in view, (
        "the page shows true and false where the reader expects 是 and 否"
    )
    assert "esc(stateLabel(item.state))" in module, (
        "the comparison state is printed without being put into words"
    )
    assert "esc(item.state)" not in module, (
        "the panel prints the state name the code uses internally"
    )
    for state in INTERNAL_STATES + ("conflict",):
        assert state in text, f"{state} has no sentence of its own"

    # The token addresses a row when the choices are sent back, so it belongs
    # in an attribute. It must not be what a person is asked to read: a visit
    # is named by its customer and when it was planned.
    for match in re.finditer(r"esc\(row\.token\)", module):
        before = module[max(0, match.start() - 40):match.start()]
        assert 'data-trip-working-token="${' in before, (
            f"the row token is shown to the reader here: ...{before[-40:]!r}"
        )
    assert "<summary>${esc(visitLabel(row))}</summary>" in module, (
        "the visit is not named where the reader looks for it"
    )
    assert "row.planned_date" in module and "row.planned_period" in module

    translated = set(re.findall(r"\['([^']+)',", i18n))
    for phrase in re.findall(r"tr\('([^']+)'", module) + re.findall(r"'([^']+)',?\n", text):
        if len(phrase) < 4 or not re.match(r"^[A-Z]", phrase):
            continue
        assert phrase in translated, f"{phrase!r} has no Chinese"

    start = _source("frontend/index.html").index('class="trip-working-import-panel"')
    panel = _source("frontend/index.html")[start:]
    panel = panel[:panel.index("</section>")]
    for literal in re.findall(r">([A-Z][^<>{}]{6,})<", panel):
        assert literal.strip() in translated, f"{literal.strip()!r} has no Chinese"


def _node(script: str) -> None:
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr or result.stdout


def check_the_import_refresh_gives_way_to_the_reader() -> None:
    """Redrawing after an import must not outrank a plan the reader is opening.

    The refresh happens because the import finished, not because anybody asked
    for it. Taking a fresh turn for it would make the plan the reader clicked
    arrive stale, leaving them on the plan they had navigated away from.
    """
    _node(r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert');
const context = { console: { error() {} }, State: { currentTripPlan: { id: 'p1' } } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-identity.js', 'utf8'), context);

// The real re-read, so that how it takes its turn is what is under test.
let refreshedWith = null;
context.ApiClient = { async getTripPlan(planId) { return { id: planId }; } };
context.populateTripPlanForm = () => {};
context.syncTripPlanListEntry = () => {};
context.renderTripPlans = () => {};
context.renderCurrentTripPlan = () => {};
context.renderTripMap = () => {};
context.TripVisitDraft = { isDirty: () => false };
context.TripPlannerModule = { renderVisitExecution() {} };
context.TripScheduleView = { renderPlan() {} };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-refresh.js', 'utf8'), context);
const realReread = context.TripPlanRefresh.reread;
context.TripPlanRefresh = {
    async reread(planId, options) { refreshedWith = options; return realReread(planId, options); },
};
context.refreshAllCounts = async () => true;
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-working-import-refresh.js', 'utf8'), context);

(async () => {
    // The import starts, and then the reader clicks another plan.
    const importTurn = context.TripPlanIdentity.current();
    const readersTurn = context.TripPlanIdentity.intend();
    const message = await context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'p1' }, text => text, importTurn);
    assert.strictEqual(message, '');
    assert.strictEqual(refreshedWith, null,
        'the planner was redrawn while the reader was opening another plan');
    assert(context.TripPlanIdentity.isCurrent(readersTurn),
        'the plan the reader opened was made stale by a refresh they never asked for');

    // With nothing else in flight, the refresh carries the number it took.
    const quietTurn = context.TripPlanIdentity.current();
    await context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'p1' }, text => text, quietTurn);
    assert.strictEqual(refreshedWith && refreshedWith.token, quietTurn,
        'the re-read did not carry the number the import took');
})().catch(error => { console.error(error); process.exit(1); });
""")


def check_a_refresh_cannot_answer_for_a_plan_the_reader_opened() -> None:
    """Out of order, the plan the reader chose is the one left on screen.

    Borrowing the number in force when the import happens to finish means the
    reader's own request and this refresh both hold it, and whichever answers
    last wins. The number is taken when the import starts instead, so a
    request made after it is strictly newer.
    """
    _node(r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert');
const context = { console: { error() {} }, State: { currentTripPlan: { id: 'A' } } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-identity.js', 'utf8'), context);

const waiting = {};
context.ApiClient = { getTripPlan(planId) {
    return new Promise(resolve => { waiting[planId] = () => resolve({ id: planId }); });
} };
for (const name of ['populateTripPlanForm', 'syncTripPlanListEntry', 'renderTripPlans',
                    'renderCurrentTripPlan', 'renderTripMap']) context[name] = () => {};
context.TripVisitDraft = { isDirty: () => false };
context.TripPlannerModule = { renderVisitExecution() {} };
context.TripScheduleView = { renderPlan() {} };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-refresh.js', 'utf8'), context);
context.refreshAllCounts = async () => true;
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-working-import-refresh.js', 'utf8'), context);

(async () => {
    // The import is started while the reader is on A.
    const importTurn = context.TripPlanIdentity.current();
    // Then the reader opens B, and B is still in flight.
    const readersTurn = context.TripPlanIdentity.intend();
    const readersPlan = context.ApiClient.getTripPlan('B').then(
        plan => context.TripPlanIdentity.accept(readersTurn, plan));

    const after = context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'A' }, text => text, importTurn);

    // B answers first, then whatever the import refresh started.
    waiting['B']();
    await readersPlan;
    if (waiting['A']) waiting['A']();
    await after;

    assert.strictEqual(context.State.currentTripPlan.id, 'B',
        'the import refresh put the reader back on the plan they had left');

    // Again, but the reader opens B only after the re-read is already running.
    context.State.currentTripPlan = { id: 'A' };
    const secondImportTurn = context.TripPlanIdentity.current();
    const secondAfter = context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'A' }, text => text, secondImportTurn);
    const laterTurn = context.TripPlanIdentity.intend();
    const laterPlan = context.ApiClient.getTripPlan('B').then(
        plan => context.TripPlanIdentity.accept(laterTurn, plan));
    waiting['B']();
    await laterPlan;
    if (waiting['A']) waiting['A']();
    await secondAfter;
    assert.strictEqual(context.State.currentTripPlan.id, 'B',
        'a re-read already in flight answered for the plan the reader opened');

    // A re-read with no number given is the reader asking, so it takes a new
    // one and whatever was in flight before it becomes stale. Reading the
    // current number instead would leave two requests holding the same one.
    const stale = context.TripPlanIdentity.intend();
    context.TripPlanRefresh.reread('C');
    assert(!context.TripPlanIdentity.isCurrent(stale),
        'a re-read the reader asked for did not take a number of its own');
})().catch(error => { console.error(error); process.exit(1); });
""")


def check_submitting_while_another_plan_loads_does_not_undo_it() -> None:
    """The plan on screen is not always the newest one asked for.

    The reader clicks plan B, and while B is still loading they submit the
    workbook for plan A, which is what they can still see. The number in force
    then belongs to B. Taking it would let the re-read of A answer as if it
    were B's, and B - which arrived first - would be replaced by A.

    So the panel takes the number the plan on screen arrived under, which is
    still A's, and that number is already stale by the time the import
    finishes.
    """
    _node(r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert');
const context = { console: { error() {} }, State: { currentTripPlan: null } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-identity.js', 'utf8'), context);

const waiting = {};
context.ApiClient = { getTripPlan(planId) {
    return new Promise(resolve => { waiting[planId] = () => resolve({ id: planId }); });
} };
for (const name of ['populateTripPlanForm', 'syncTripPlanListEntry', 'renderTripPlans',
                    'renderCurrentTripPlan', 'renderTripMap']) context[name] = () => {};
context.TripVisitDraft = { isDirty: () => false };
context.TripPlannerModule = { renderVisitExecution() {} };
context.TripScheduleView = { renderPlan() {} };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-refresh.js', 'utf8'), context);
let countsRefreshed = 0;
let navigationCounts = 0;
context.refreshAllCounts = async () => { countsRefreshed += 1; return true; };
context.refreshNavigationCounts = async () => { navigationCounts += 1; return true; };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-working-import-refresh.js', 'utf8'), context);

(async () => {
    // Plan A is opened and arrives.
    const aTurn = context.TripPlanIdentity.intend();
    const aLoaded = context.ApiClient.getTripPlan('A').then(
        plan => context.TripPlanIdentity.accept(aTurn, plan));
    waiting['A']();
    await aLoaded;
    assert.strictEqual(context.State.currentTripPlan.id, 'A');

    // The reader clicks B. It is still loading, so A is still on screen.
    const bTurn = context.TripPlanIdentity.intend();
    const bLoaded = context.ApiClient.getTripPlan('B').then(
        plan => context.TripPlanIdentity.accept(bTurn, plan));

    // They submit A's workbook, which is what they can still see.
    const planTurn = context.TripPlanIdentity.accepted();
    assert.strictEqual(planTurn, aTurn,
        'the panel took the number of the plan that is still loading');
    const after = context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'A' }, text => text, planTurn);

    waiting['B']();
    await bLoaded;
    if (waiting['A']) waiting['A']();
    await after;

    assert.strictEqual(context.State.currentTripPlan.id, 'B',
        'importing plan A put the reader back on A after they had opened B');
    assert.strictEqual(countsRefreshed, 0,
        'the module was reloaded while the reader was still opening another plan');
    assert.strictEqual(navigationCounts, 1,
        'the numbers beside the module names were left showing the old totals');
})().catch(error => { console.error(error); process.exit(1); });
""")


def check_opening_a_plan_during_the_re_read_still_wins() -> None:
    """The reader can move on after the refresh has already started waiting.

    The re-read of the imported plan is in flight when they open another one.
    It correctly refuses its own answer - but the full refresh that follows it
    reloads whatever module is open, and that takes a newer number than the
    plan they are waiting for. So the number is checked again after the wait,
    and only the numbers beside the module names are touched.
    """
    _node(r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert');
const context = { console: { error() {} }, State: { currentTripPlan: null } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-identity.js', 'utf8'), context);

const waiting = {};
context.ApiClient = { getTripPlan(planId) {
    return new Promise(resolve => { waiting[planId] = () => resolve({ id: planId }); });
} };
for (const name of ['populateTripPlanForm', 'syncTripPlanListEntry', 'renderTripPlans',
                    'renderCurrentTripPlan', 'renderTripMap']) context[name] = () => {};
context.TripVisitDraft = { isDirty: () => false };
context.TripPlannerModule = { renderVisitExecution() {} };
context.TripScheduleView = { renderPlan() {} };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-refresh.js', 'utf8'), context);

let fullRefreshes = 0;
let navigationCounts = 0;
// The full refresh reloads the open module, which is what claims the screen.
context.refreshAllCounts = async () => {
    fullRefreshes += 1;
    context.TripPlanIdentity.intend();
    return true;
};
context.refreshNavigationCounts = async () => { navigationCounts += 1; return true; };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-working-import-refresh.js', 'utf8'), context);

(async () => {
    const aTurn = context.TripPlanIdentity.intend();
    const aLoaded = context.ApiClient.getTripPlan('A').then(
        plan => context.TripPlanIdentity.accept(aTurn, plan));
    waiting['A']();
    await aLoaded;

    // The import finishes and its re-read of A starts waiting.
    const after = context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'A' }, text => text,
        context.TripPlanIdentity.accepted());
    await Promise.resolve();

    // Only now does the reader open B.
    const bTurn = context.TripPlanIdentity.intend();
    const bLoaded = context.ApiClient.getTripPlan('B').then(
        plan => context.TripPlanIdentity.accept(bTurn, plan));

    // A's re-read answers first and is refused; then B answers.
    if (waiting['A']) waiting['A']();
    await after;
    waiting['B']();
    const accepted = await bLoaded;

    assert.strictEqual(fullRefreshes, 0,
        'the module was reloaded after the reader had opened another plan');
    assert.strictEqual(navigationCounts, 1,
        'the numbers were left showing the totals from before the import');
    assert.strictEqual(accepted, true,
        'the plan the reader opened was refused because of a refresh they never asked for');
    assert.strictEqual(context.State.currentTripPlan.id, 'B',
        'the reader was put back on the plan the workbook came from');
})().catch(error => { console.error(error); process.exit(1); });
""")


def check_a_refresh_that_failed_is_not_reported_as_done() -> None:
    """Counts that did not refresh are said out loud, not left looking stale."""
    _node(r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert');
const context = { console: { error() {} }, State: { currentTripPlan: { id: 'p1' } } };
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-plan-identity.js', 'utf8'), context);
context.TripPlanRefresh = { async reread() {} };
vm.runInContext(fs.readFileSync('frontend/js/modules/trip-working-import-refresh.js', 'utf8'), context);

(async () => {
    context.refreshAllCounts = async () => false;
    const said = await context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'p1' }, text => text);
    assert(said.includes('could not be refreshed'),
        `counts failed to refresh and the page said nothing: ${JSON.stringify(said)}`);

    context.refreshAllCounts = async () => true;
    context.TripPlanRefresh = { async reread() { throw new Error('offline'); } };
    const alsoSaid = await context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'p1' }, text => text);
    assert(alsoSaid.includes('could not be refreshed'), alsoSaid);

    context.TripPlanRefresh = { async reread() {} };
    assert.strictEqual(await context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'p1' }, text => text), '');

    // And on the branch where the reader has moved on: the numbers are still
    // refreshed, and a failure there is still said out loud.
    const staleToken = context.TripPlanIdentity.accepted();
    context.TripPlanIdentity.intend();
    context.refreshNavigationCounts = async () => false;
    const stale = await context.TripWorkingImportRefresh.after(
        { status: 'completed', plan_id: 'p1' }, text => text, staleToken);
    assert(stale.includes('could not be refreshed'), JSON.stringify(stale));
})().catch(error => { console.error(error); process.exit(1); });
""")
    # The helper it depends on has to be able to say it failed.
    counts = _source("frontend/js/modules/refresh-counts.js")
    assert "return false;" in counts and "return true;" in counts, (
        "refreshAllCounts keeps its failures entirely to itself again"
    )
    # The numbers can be refreshed without redrawing whatever is open.
    body = counts[counts.index("async function refreshNavigationCounts("):]
    body = body[:body.index("\nasync function refreshAllCounts(")]
    assert "loadModuleData" not in body, (
        "refreshing the numbers reloads the open module, so it cannot be used "
        "while the reader is opening something else"
    )
    assert "applyNavigationCounts" in body


def run() -> None:
    check_the_panel_is_wired()
    check_the_choice_is_carried_with_the_preview_it_was_made_on()
    check_nothing_internal_reaches_the_reader()
    check_the_import_refresh_gives_way_to_the_reader()
    check_a_refresh_cannot_answer_for_a_plan_the_reader_opened()
    check_submitting_while_another_plan_loads_does_not_undo_it()
    check_opening_a_plan_during_the_re_read_still_wins()
    check_a_refresh_that_failed_is_not_reported_as_done()
    print("PASS: field-workbook import frontend contract")


if __name__ == "__main__":
    run()
