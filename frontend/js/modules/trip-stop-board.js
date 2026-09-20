/** How the reorder list is read: the counts, the order, and what is filtered.
 *
 * Order and filter are ways of looking, never a change to the plan. Nothing is
 * re-rendered to apply them - the rows stay exactly where they are and only
 * their position and visibility change - and Up/Down are switched off outside
 * plan order instead of quietly moving a stop to a place the reader cannot
 * see: in a list sorted by date, "down" has no meaning the plan would keep.
 *
 * Kind and timing are two questions, not one list of six answers: "customer or
 * hotel" and "is this time still ours to move" are asked together often enough
 * that folding them into a single filter made one of them unreachable.
 *
 * The three timings are decided here, so the row, the counts and the filter can
 * never disagree about one stop.
 */
(function () {
    'use strict';

    const KINDS = Object.freeze(['all', 'customer', 'free']);
    const TIMINGS = Object.freeze(['all', 'agreed', 'flexible', 'unscheduled']);
    const ORDERS = Object.freeze(['plan', 'date', 'timing', 'name']);
    const TIMING_ORDER = Object.freeze(['agreed', 'flexible', 'unscheduled']);
    const UNDATED = '9999-12-31';   // no date yet: read last, never first
    const state = { kind: 'all', timing: 'all', order: 'plan' };

    const isFree = stop => stop?.stop_kind === 'free';
    const nameOf = stop => String(stop?.customer_name || stop?.location_name || '');
    const key = id => String(id ?? '');

    function timing(stop) {
        if (stop?.schedule_locked) return 'agreed';
        return stop?.planned_date ? 'flexible' : 'unscheduled';
    }

    function matches(stop) {
        const kindOk = state.kind === 'all'
            || (state.kind === 'free' ? isFree(stop) : !isFree(stop));
        return kindOk && (state.timing === 'all' || timing(stop) === state.timing);
    }

    function counts(stops = []) {
        return {
            all: stops.length,
            customer: stops.filter(stop => !isFree(stop)).length,
            free: stops.filter(isFree).length,
            agreed: stops.filter(stop => timing(stop) === 'agreed').length,
            flexible: stops.filter(stop => timing(stop) === 'flexible').length,
            unscheduled: stops.filter(stop => timing(stop) === 'unscheduled').length,
            shown: stops.filter(matches).length,
        };
    }

    // Every entry keeps the position it has in the plan, because that is what
    // Up and Down move and what the sequence numbers on screen mean.
    function ordered(stops = []) {
        const entries = stops.map((stop, index) => ({ stop, index }));
        const compare = {
            date: (left, right) => String(left.stop.planned_date || UNDATED)
                .localeCompare(String(right.stop.planned_date || UNDATED)),
            timing: (left, right) => TIMING_ORDER.indexOf(timing(left.stop)) - TIMING_ORDER.indexOf(timing(right.stop)),
            name: (left, right) => nameOf(left.stop).localeCompare(nameOf(right.stop)),
        }[state.order];
        if (!compare) return entries;
        return entries.sort((left, right) => compare(left, right) || left.index - right.index);
    }

    function rows() {
        return Array.from(document.querySelectorAll('#trip-stop-order-list .trip-order-row[data-stop-id]'));
    }

    // Outside plan order the buttons would move a stop against a list that is
    // not the plan's, so they say why they are off rather than just being grey.
    function moves(row, index, total) {
        const frozen = state.order !== 'plan';
        Array.from(row.querySelectorAll('[data-move]')).forEach(button => {
            const up = button.dataset.move === 'up';
            button.disabled = frozen || (up ? index === 0 : index === total - 1);
            button.title = frozen
                ? (window.I18n?.t?.('Switch back to plan order to move a stop.') || '') : '';
        });
    }

    function apply(stops) {
        const list = stops || State.currentTripPlan?.stops || [];
        const places = new Map();
        ordered(list).forEach((entry, position) => places.set(key(entry.stop.id), { entry, position }));
        rows().forEach(row => {
            const found = places.get(key(row.dataset.stopId));
            if (!found) return;
            row.style.order = String(found.position);
            row.hidden = !matches(found.entry.stop);
            moves(row, found.entry.index, list.length);
        });
    }

    function redraw() {
        apply();
        window.TripStopBoardView?.render?.();
    }

    function setKind(value) {
        state.kind = KINDS.includes(value) ? value : 'all';
        redraw();
    }

    function setTiming(value) {
        state.timing = TIMINGS.includes(value) ? value : 'all';
        redraw();
    }

    function setOrder(value) {
        state.order = ORDERS.includes(value) ? value : 'plan';
        redraw();
    }

    window.TripStopBoard = Object.freeze({
        KINDS, TIMINGS, ORDERS, timing, matches, counts, ordered, apply,
        setKind, setTiming, setOrder,
        kind: () => state.kind,
        timingFilter: () => state.timing,
        order: () => state.order,
    });
})();
