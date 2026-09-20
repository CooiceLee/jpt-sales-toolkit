/** Changing the order of the stops - on purpose, in its own place.
 *
 * The timeline is read by date. Up and Down have no meaning there: "down" in a
 * list sorted by day would either do nothing visible or move a stop somewhere
 * the reader cannot see. So reordering is a thing you open, and while it is
 * open the stops are shown in the order the plan actually stores them.
 *
 * One line per stop, no forms: the form for a stop is in the panel beside the
 * timeline, and two copies of it would be two sets of the same field ids.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const LABELS = Object.freeze({
        agreed: 'Time agreed', flexible: 'Time adjustable', unscheduled: 'No date yet',
    });

    function row(stop, index, total) {
        const timing = window.TripStopBoard?.timing?.(stop) || 'flexible';
        const name = stop.customer_name || stop.location_name || t('Untitled');
        const selected = window.TripSelection?.is?.('stop', stop.id);
        return `<div class="trip-order-row${selected ? ' is-selected' : ''}" data-stop-id="${h(stop.id)}"
            data-stop-kind="${h(stop.stop_kind === 'free' ? 'free' : 'customer')}"
            data-stop-timing="${h(timing)}">
            <button type="button" class="trip-order-name" onclick="TripSelection.select('stop', '${h(stop.id)}')">
                <span class="trip-order-seq">${h(index + 1)}</span>
                <strong data-business>${h(name)}</strong>
                <span class="trip-stop-flag is-${h(timing)}">${h(t(LABELS[timing]))}</span>
            </button>
            <div class="trip-stop-actions">
                <button type="button" class="btn btn-secondary btn-sm" data-move="up"
                    onclick="moveTripStop('${h(stop.id)}', -1)" ${index === 0 ? 'disabled' : ''}>${h(t('Up'))}</button>
                <button type="button" class="btn btn-secondary btn-sm" data-move="down"
                    onclick="moveTripStop('${h(stop.id)}', 1)" ${index === total - 1 ? 'disabled' : ''}>${h(t('Down'))}</button>
                <button type="button" class="btn btn-secondary btn-sm" onclick="${stop.stop_kind === 'free'
                    ? `TripFreeStopActions.archive('${h(stop.id)}')` : `removeTripStop('${h(stop.id)}')`}">${h(t('Remove'))}</button>
            </div>
        </div>`;
    }

    function render(plan = State.currentTripPlan) {
        const root = document.getElementById('trip-stop-order-list');
        if (!root) return;
        // The order in force, not the stored one: a move the reader made is
        // what they are looking at until the route is saved.
        const stops = window.TripStopOrder?.stops?.(plan?.stops || [])
            || (plan?.stops || []);
        root.innerHTML = stops.length
            ? stops.map((stop, index) => row(stop, index, stops.length)).join('')
            : `<div class="empty-state compact">${h(t('No stops yet'))}</div>`;
        window.TripStopBoard?.apply?.(stops);
        window.TripStopBoardView?.render?.(stops);
    }

    window.TripStopOrderView = Object.freeze({ render });
})();
