/** The line above the reorder list: how many stops, and how to look at them.
 *
 * Kind and timing are two different questions - "is this a customer or a hotel"
 * and "is this time ours to move" - and six equal-weight chips across the top
 * made choosing how to look harder than reading. Two small selects say the same
 * thing, and the count beside them says how much the current answer leaves.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const KINDS = [['all', 'All stops'], ['customer', 'Customer visits'], ['free', 'Personal stops']];
    const TIMINGS = [['all', 'Any time status'], ['agreed', 'Time agreed'],
        ['flexible', 'Time adjustable'], ['unscheduled', 'No date yet']];
    const ORDERS = [['plan', 'Plan order'], ['date', 'By date'],
        ['timing', 'By time status'], ['name', 'By name']];

    function select(id, options, chosen, handler, label) {
        return `<label class="trip-board-sort"><span>${h(t(label))}</span>
            <select class="form-input" id="${h(id)}" onchange="${handler}">${options
                .map(([value, text]) => `<option value="${h(value)}" ${
                    value === chosen ? 'selected' : ''}>${h(t(text))}</option>`).join('')}</select></label>`;
    }

    /**
     * The order on screen is the one in force; saving is what writes it.
     *
     * A move lives in the draft until the route is saved, and the preview it
     * triggers comes back with the stops in their stored order. The list shows
     * what the reader arranged - so the honest thing left to say is that it is
     * not written yet, and that the dates above still come from the last
     * calculation rather than from this arrangement.
     */
    function pending() {
        if (!window.TripStopOrder?.pending?.(State.currentTripPlan?.stops || [])) return '';
        return `<p class="trip-board-note is-pending">${h(t(
            'This order is not saved yet. Choose "Calculate & save route" to write it; '
            + 'the dates above still come from the last calculation.'))}</p>`;
    }

    // Two things a reader can be left staring at: a filter that matches nothing
    // and greyed-out Up/Down buttons. Both say what to do about it.
    function note(board, counts) {
        if (!counts.shown && counts.all) {
            return `<p class="trip-board-note">${h(t('No stop matches this filter.'))}
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripStopBoard.setKind('all'); TripStopBoard.setTiming('all')">${
                    h(t('Show all stops'))}</button></p>`;
        }
        if (board.order() !== 'plan') {
            return `<p class="trip-board-note">${h(t(
                'This is a way of looking at the plan, not its order. Switch back to plan order to move a stop.'
            ))}</p>`;
        }
        return '';
    }

    function render(stops) {
        const root = document.getElementById('trip-stop-board');
        if (!root) return;
        const board = window.TripStopBoard;
        const list = stops || State.currentTripPlan?.stops || [];
        if (!board || !list.length) { root.innerHTML = ''; return; }
        const counts = board.counts(list);
        root.innerHTML = `<div class="trip-board-tools">
                ${select('trip-stop-kind', KINDS, board.kind(), 'TripStopBoard.setKind(this.value)', 'Kind')}
                ${select('trip-stop-timing', TIMINGS, board.timingFilter(), 'TripStopBoard.setTiming(this.value)', 'Time status')}
                ${select('trip-stop-order', ORDERS, board.order(), 'TripStopBoard.setOrder(this.value)', 'Order')}
                <span class="trip-board-total">${h(counts.shown === counts.all
                    ? t('{count} stops', { count: counts.all })
                    : t('Showing {count} of {total} stops', { count: counts.shown, total: counts.all }))}</span>
            </div>
            ${pending()}${note(board, counts)}`;
    }

    window.TripStopBoardView = Object.freeze({ render });
})();
