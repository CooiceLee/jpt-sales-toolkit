"""One judgement about the route, in one place, said from all four zones.

Three places used to decide whether the route was usable and they disagreed:
the settings card looked only at the local draft and said "Route settings match
the saved plan" while the server had already marked the itinerary out of date,
and the export panel - which does check that - refused the download. A reader
who had just been told everything matched then met a disabled button.

The card that held the only preview and save buttons is hidden in three of the
four zones, so somebody adjusting the order in the route zone had to go back to
settings to do anything about what they had just changed.

What is checked here: the derivation says the true thing in each situation, the
bar the zones share is the only place with those buttons, and an editor holding
unsaved work refuses the action *and* offers the way back to it.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / "frontend" / "js" / "modules"
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


def check_the_bar_is_where_every_zone_can_see_it() -> None:
    bar = INDEX[INDEX.index('id="trip-route-bar"'):]
    for element in ("trip-route-status", "trip-route-preview", "trip-route-save"):
        assert element in bar[:1200], f"{element} is not in the shared bar"
    zone_bar = INDEX[INDEX.index('class="trip-zone-bar"'):INDEX.index('data-trip-zone="settings"')]
    assert 'id="trip-route-bar"' in zone_bar, (
        "the bar is not in the zone bar, so three of the four zones hide it"
    )
    settings = INDEX[INDEX.index('data-trip-zone="settings"'):INDEX.index('class="trip-layout"')]
    for duplicate in ("previewCurrentTripItinerary()", "generateCurrentTripItinerary()",
                      'id="trip-draft-status"'):
        assert duplicate not in settings, (
            f"the settings card still carries {duplicate}: two copies of the same "
            "action are two answers to 'did this save'"
        )


def check_one_module_decides_and_the_others_ask_it() -> None:
    export = (MODULES / "trip-export-naming.js").read_text(encoding="utf-8")
    assert "TripRouteState" in export, (
        "the export panel judges the route itself again instead of asking the "
        "shared derivation"
    )
    transport = (MODULES / "trip-transport-view.js").read_text(encoding="utf-8")
    assert "Route settings match the saved plan" not in transport, (
        "the settings card still calls a stale route 'matching the saved plan'"
    )
    briefing = (MODULES / "trip-briefing-actions.js").read_text(encoding="utf-8")
    assert "needs recalculating" in briefing, (
        "saving a preparation that invalidated the route says only that the "
        "preparation was saved"
    )


HARNESS = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

const context = {
  console,
  I18n: { t: (text, params = {}) => Object.entries(params)
    .reduce((acc, [key, value]) => acc.split('{' + key + '}').join(value), text) },
};
context.window = context;
vm.createContext(context);
for (const name of ['trip-open-editors.js', 'trip-route-state.js']) {
  vm.runInContext(fs.readFileSync('frontend/js/modules/' + name, 'utf8'),
                  context, { filename: name });
}

const derive = (plan, draft, extra = {}) => {
  Object.assign(context, {
    State: { currentTripPlan: plan, tripBusy: Boolean(extra.busy) },
    TripPlanningDraft: { get: () => draft },
    TripBriefingDraft: { isDirty: () => Boolean(extra.briefingDirty) },
    TripFreeStopDraft: { isDirty: () => Boolean(extra.freeStopDirty) },
    TripFreeStopForm: { isOpen: () => Boolean(extra.freeStopOpen) },
    TripVisitDraft: { isDirty: () => Boolean(extra.visitDirty) },
  });
  return context.TripRouteState.derive();
};

const saved = { id: 'p1', itinerary_generated_at: '2026-09-10T00:00:00Z',
  itinerary_summary: { valid: true, stale: false } };
const stale = { id: 'p1', itinerary_generated_at: '2026-09-10T00:00:00Z',
  itinerary_summary: { valid: false, stale: true,
    warnings: ['A saved visit location changed. Preview and save the route again.'] } };
const unworkable = { id: 'p1', itinerary_generated_at: '2026-09-10T00:00:00Z',
  itinerary_summary: { valid: true, stale: false,
    risks: [{ kind: 'cannot_reach_booked_visit' }, { kind: 'booked_on_skipped_day' }] } };
const clean = { dirty: false, previewReady: false };

// Saved and valid.
let state = derive(saved, clean);
assert.equal(state.headline.text, 'Route saved');
assert.ok(state.actions.download.enabled);
assert.equal(state.nextStep, null);

// Saved, and the server says the route it produced is out of date. This is the
// case the settings card used to call "matching the saved plan".
state = derive(stale, clean);
assert.match(state.headline.text, /needs recalculating/,
  'a route the server marked out of date was reported as matching the saved plan');
assert.equal(state.actions.download.enabled, false);
assert.match(state.actions.download.reason, /out of date/);
assert.equal(state.nextStep.kind, 'preview');

// A preview is not a save.
state = derive(saved, { dirty: true, previewReady: true });
assert.match(state.headline.text, /Not saved yet/);
assert.equal(state.actions.download.enabled, false);
assert.equal(state.nextStep.kind, 'save');

// Edited, not previewed.
state = derive(saved, { dirty: true, previewReady: false });
assert.match(state.headline.text, /Unsaved route changes/);
assert.equal(state.nextStep.kind, 'preview');

// Saved, and still not a trip anybody can make.
state = derive(unworkable, clean);
assert.match(state.headline.text, /do not work/,
  'an agreed visit nobody can reach was reported as simply saved');
assert.equal(state.blockingRisks.length, 1, 'a soft risk was counted as a blocker');
assert.equal(state.nextStep.kind, 'risks');

// An open editor refuses the route actions - and only those.
for (const [flag, label] of [['briefingDirty', /visit preparation/],
                             ['freeStopDirty', /personal stop/],
                             ['visitDirty', /visit record/]]) {
  state = derive(saved, clean, { [flag]: true });
  assert.equal(state.actions.save.enabled, false, `${flag} did not hold the save`);
  assert.equal(state.actions.preview.enabled, false);
  assert.match(state.actions.save.reason, label);
  assert.equal(state.nextStep.kind, 'editor');
  assert.ok(state.nextStep.editor.zone, 'the blocking editor does not say where it is');
  assert.ok(state.actions.download.enabled,
    'an unsaved editor blocked the download, which it has nothing to do with');
}

// Busy is its own situation, and not a success message.
state = derive(saved, clean, { busy: true });
assert.equal(state.headline.tone, 'busy');
assert.equal(state.actions.preview.enabled, false);
assert.equal(state.actions.save.enabled, false);
assert.match(state.actions.save.reason, /already running/);

// No plan: nothing claims anything.
state = derive(null, null);
assert.equal(state.actions.save.enabled, false);
assert.equal(state.actions.download.enabled, false);
console.log(JSON.stringify({ ok: true }));
"""


def check_the_derivation_says_the_true_thing() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(HARNESS)
        script = handle.name
    result = subprocess.run(["node", script], capture_output=True, text=True, cwd=ROOT)
    Path(script).unlink(missing_ok=True)
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(result.stdout.strip().splitlines()[-1])["ok"]


def check_the_two_buttons_say_how_they_relate() -> None:
    """Looking at a preview, the two buttons read as a sequence.

    Try it, confirm it, save the thing I confirmed - which is not what happens:
    saving works the route out again from the same settings rather than storing
    the preview. Measured on a real plan, the two produce the same 73 schedule
    items and the same risks when nothing changes in between, so the wording
    says that rather than leaving it to be guessed.
    """
    bar = (MODULES / "trip-route-bar.js").read_text(encoding="utf-8")
    assert "state.previewReady && state.draftDirty" in bar, (
        "nothing tells the reader what saving does to the preview they are "
        "looking at"
    )
    assert "A trial is not saved; saving works the route out again." in bar, (
        "the short sentence the bar has room for is gone"
    )
    assert "next.title = tr(" in bar, (
        "the full answer is nowhere: the bar's one line cannot hold it, so it "
        "has to be reachable rather than cut off"
    )
    css = (ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
    rule = css[css.index(".trip-route-next {"):css.index(".trip-route-next.blocked")]
    assert "text-overflow: ellipsis" not in rule and "nowrap" not in rule, (
        "the reason an action is refused is truncated mid-sentence, and that is "
        f"the one line the reader has to act on: {rule}"
    )
    i18n = (ROOT / "frontend" / "js" / "i18n.js").read_text(encoding="utf-8")
    assert "试算不写入计划" in i18n, "the short sentence is not translated"
    assert "不写入已保存的计划" in i18n, (
        "the full explanation still claims a trial changes nothing - it does "
        "change what is on screen"
    )
    assert "['Preview route', '试算路线（不保存）']" in i18n, (
        "the preview button reads as a step before saving rather than as a "
        "trial that keeps nothing"
    )


def check_a_blocked_action_offers_the_way_back() -> None:
    bar = (MODULES / "trip-route-bar.js").read_text(encoding="utf-8")
    assert "goToBlocker" in bar, "nothing takes the reader to the editor that is refusing"
    assert "TripZones?.show?.(editor.zone)" in bar, (
        "the way back does not open the zone the editor lives in"
    )
    assert "focusEditor?.(editor.kind, editor.stopId || editor.userId)" in bar, (
        "the way back names a kind of editor without saying which one: visit "
        "execution has a card per stop and the team card a row per member, so "
        "a kind alone arrives nowhere"
    )
    for forbidden in ("saveFollowUp", "putTripBriefing", "submit()"):
        assert forbidden not in bar, (
            f"the bar calls {forbidden}: it must never submit somebody's "
            "half-written editor for them"
        )
    focus = (MODULES / "trip-route-focus.js").read_text(encoding="utf-8")
    assert "TripBriefingReveal" in focus, (
        "the focus helper reaches for the preparation editor itself instead of "
        "the one path that reveals it"
    )
    assert "remembered" in focus and "forget" in focus, (
        "zone positions are not remembered per plan, so another plan inherits "
        "the last one's depth"
    )


def main() -> None:
    check_the_bar_is_where_every_zone_can_see_it()
    check_one_module_decides_and_the_others_ask_it()
    check_the_derivation_says_the_true_thing()
    check_the_two_buttons_say_how_they_relate()
    check_a_blocked_action_offers_the_way_back()
    print("PASS: one route judgement, shown in every zone, with a way back from "
          "a blocked action")


if __name__ == "__main__":
    main()
