/** Whether the dates on a stop's card are older than what has been typed.
 *
 * The duration box writes to the route draft; the dates beside it come from the
 * last calculation. Typing "2 days" therefore leaves a two-day stay sitting over
 * a one-day schedule, and with nothing between them neither can be trusted -
 * which is what "I entered 2 days and the dates still say one" was.
 *
 * Said at the moment the number changes, because typing redraws nothing and the
 * note would otherwise wait for some unrelated redraw to appear.
 */
(function () {
    'use strict';

    /** The half-days waiting to be calculated, or 0 when the dates are current. */
    function half(stop) {
        const draft = window.TripPlanningDraft?.get?.();
        if (!draft || !stop) return 0;
        const wanted = draft.stopDurations?.[stop.id]?.half_days;
        if (wanted == null) return 0;
        const saved = window.TripDuration?.readStopDuration?.(stop);
        return Number(wanted) === Number(saved) ? 0 : Number(wanted);
    }

    function card(stopId) {
        return Array.from(document.querySelectorAll('#trip-current-plan .trip-stop[data-stop-id]'))
            .find(element => element.dataset.stopId === String(stopId)) || null;
    }

    function mark(stopId) {
        const element = card(stopId);
        const stop = (State.currentTripPlan?.stops || [])
            .find(item => String(item.id) === String(stopId));
        if (!element || !stop) return;
        const pending = half(stop);
        let line = element.querySelector('.trip-stop-pending');
        if (!pending) { line?.remove(); return; }
        if (!line) {
            line = document.createElement('div');
            line.className = 'trip-stop-pending';
            element.querySelector('.trip-stop-schedule')?.after(line);
        }
        line.textContent = I18n.t('Last calculated result. Waiting to be updated: {count} days.', {
            count: TripDuration.toDisplayDays(pending),
        });
    }

    window.TripStopPending = Object.freeze({ half, mark });
    window.tripStopMarkPending = mark;
})();
