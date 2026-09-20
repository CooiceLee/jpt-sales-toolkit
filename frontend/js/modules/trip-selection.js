/** What the reader is looking at, so one thing is edited in one place.
 *
 * The timeline answers "when", the panel beside it answers "and what about
 * it": choosing a visit or a journey on the line opens that one object's own
 * form, instead of a second full list underneath with every form open at once.
 *
 * A selection is a claim about an object in the plan on screen, so it is kept
 * as the object's identity and re-read each time it is drawn - never as the
 * rendered element, which is replaced by the next redraw, and never as a
 * position in a list, which moves when the plan does.
 */
(function () {
    'use strict';

    let current = null;                    // { kind: 'stop' | 'leg', id, members }

    /**
     * What identifies the thing that is selected.
     *
     * A stop is its own id. A journey is not: two colleagues can hold the same
     * leg_key and travel it on different days, and the row that carries the
     * facts - dates, distance, hours - is one row per set of those facts, not
     * one per connection. Matching on the connection alone highlighted both
     * members' rows while the panel edited one of them.
     *
     * So a journey is the connection *and* whose journey it is. Genuinely
     * shared travel is one row naming everybody on it, and its member set is
     * what it is matched by.
     */
    const memberKey = list => [...new Set((list || []).filter(Boolean).map(String))].sort().join(',');

    function same(left, right) {
        if (!left || !right || left.kind !== right.kind) return false;
        if (String(left.id) !== String(right.id)) return false;
        return left.kind !== 'leg' || memberKey(left.members) === memberKey(right.members);
    }

    function draw() {
        window.renderCurrentTripPlan?.();
        window.TripTimelineView?.mark?.();
    }

    /**
     * The map follows the selection, quietly.
     *
     * It centres on what was chosen so the two agree, and stops there: being
     * thrown up to the map every time a row is clicked is not what somebody
     * working through a day's visits asked for. "Show on the map" is the
     * button that finishes the journey - see trip-map-focus.js.
     */
    function showOnMap(selection) {
        if (!selection) return;
        if (selection.kind === 'stop') return window.TripTeamMap?.focusStop?.(selection.id);
        window.TripTeamMap?.focusLeg?.(selection.id, selection.mode || '', selection.memberId || '');
    }

    // Where the panel is stacked under the timeline there is no "beside it" to
    // look at, so choosing something brings it into view - the reader's own
    // click, followed through, rather than the page moving on its own.
    function reveal() {
        const panel = document.querySelector('.trip-detail-panel');
        const workspace = document.querySelector('.trip-schedule-workspace');
        if (!panel || !workspace) return;
        const stacked = panel.getBoundingClientRect().top
            > workspace.getBoundingClientRect().top + 40;
        if (stacked) panel.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    /**
     * The field somebody came for, in view and ready to type in.
     *
     * Focus alone is not enough: the caret can be in a box that is behind the
     * pinned bar or below the fold, and "nothing happened" is what that looks
     * like. The block is brought into view first - scroll-margin keeps it clear
     * of the bar - and only then does the date take the caret.
     */
    function revealTask(kind, id, intent) {
        if (kind !== 'stop' || intent !== 'agree') return;
        window.setTimeout(() => {
            const block = document.getElementById(`stop-agree-fields-${id}`);
            const field = document.getElementById(`stop-agreed-date-${id}`);
            const task = block?.closest('.trip-detail-body') ? block : block;
            task?.scrollIntoView({ block: 'center', behavior: 'smooth' });
            if (field && !field.disabled) field.focus({ preventScroll: true });
        }, 80);
    }

    function select(kind, id, extra = {}) {
        if (!id || !['stop', 'leg'].includes(kind)) return;
        // Something typed into another visit is not carried along by clicking
        // away from it: the same rule every other local editor here follows.
        if (window.TripStopTyping?.guard?.(kind === 'stop' ? id : null)) return;
        const members = extra.members || (extra.memberId ? [extra.memberId] : []);
        current = Object.freeze({ kind, id: String(id), ...extra, members: [...members] });
        draw();
        showOnMap(current);
        reveal();
        revealTask(kind, String(id), extra.intent);
    }

    function clear() {
        if (!current) return;
        current = null;
        draw();
    }

    /**
     * Keep the selection only while the plan still holds it.
     *
     * A stop removed elsewhere, or a plan switched underneath, must not leave a
     * form open on something that is no longer there - and must not silently
     * re-point at whatever now happens to sit in that position.
     */
    function reconcile(plan) {
        if (!current) return null;
        // A journey survives while the plan still holds it *for all of these
        // people*: one of them leaving makes it a different journey, and
        // quietly narrowing the selection to whoever is left would edit
        // something the reader never chose. Falling back to another row with
        // the same connection would do the same.
        const holds = member => (plan?.legs || []).some(leg =>
            String(leg.leg_key) === current.id && String(leg.member_id) === String(member));
        const alive = current.kind === 'stop'
            ? (plan?.stops || []).some(stop => String(stop.id) === current.id)
            : (current.members.length
                ? current.members.every(holds)
                : (plan?.legs || []).some(leg => String(leg.leg_key) === current.id));
        if (!alive) {
            const wasLeg = current.kind === 'leg';
            current = null;
            if (wasLeg) {
                window.notify?.(window.I18n?.t?.(
                    'That journey is no longer in the plan. Choose one on the timeline again.'
                ) || '');
            }
        }
        return current;
    }

    window.TripSelection = Object.freeze({
        select, clear, reconcile, same, memberKey,
        get: () => current,
        is: (kind, id, members) => same(current, { kind, id, members }),
    });
})();
