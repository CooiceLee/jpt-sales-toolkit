/** Route-form binding and validation kept separate from draft mutation actions. */
(function() {
    const ROUTE_FIELD_IDS = Object.freeze([
        'trip-title', 'trip-start-date', 'trip-end-date', 'trip-plan-region',
        'trip-planning-mode',
        'trip-origin-name', 'trip-origin-lat', 'trip-origin-lng',
        'trip-destination-name', 'trip-destination-lat', 'trip-destination-lng',
        'trip-avoid-weekends', 'trip-holidays', 'trip-description',
    ]);
    const boundFields = new WeakSet();
    let unloadBound = false;

    function validationError(payload = {}) {
        const invalidLegDuration = [...(document.querySelectorAll?.('[data-leg-duration-half-days]') || [])]
            .some(input => String(input.value ?? '').trim()
                && TripDuration.parseDisplayTravelDays(input.value) == null);
        if (invalidLegDuration) {
            return 'Travel duration must be 0 to 30 days in 0.5-day increments.';
        }
        const overrides = Object.values(payload.leg_overrides || {});
        const priority = payload.transport_mode_priority || [];
        const legs = State.currentTripPlan?.legs || [];
        const validManualOther = item => item?.selected_mode === 'other'
            && (Number(item.manual_time_hours) > 0 || Number(item.manual_travel_half_days) > 0);
        if (priority.length === 1 && priority[0] === 'other'
            && (!legs.length || legs.some(leg => !validManualOther(payload.leg_overrides?.[leg.leg_key])))) {
            return 'When Other is the only transport mode, keep an estimated mode for the first preview, then set Other with manual hours or days on every leg.';
        }
        if (overrides.some(item => item?.selected_mode === 'other'
            && !validManualOther(item))) {
            return 'Other transport requires manual travel hours or travel days before previewing.';
        }
        const windows = [
            ['departure_window_start', 'departure_window_end'],
            ['return_window_start', 'return_window_end'],
        ];
        if (windows.some(([start, end]) => payload[start] && payload[end] && payload[start] > payload[end])) {
            return 'A travel window start must not be later than its end.';
        }
        const activeIds = (State.currentTripPlan?.stops || []).map(stop => String(stop.id));
        const order = (payload.stop_order || []).map(String);
        if (payload.route_order_mode === 'manual' && activeIds.length && (order.length !== activeIds.length
            || new Set(order).size !== order.length
            || activeIds.some(id => !order.includes(id)))) {
            return 'The draft stop order is incomplete. Refresh the plan and try again.';
        }
        return null;
    }

    function init() {
        ROUTE_FIELD_IDS.forEach(id => {
            const element = document.getElementById(id);
            if (!element || boundFields.has(element) || typeof element.addEventListener !== 'function') return;
            boundFields.add(element);
            element.addEventListener('change', () => {
                window.TripChinaHubs?.markCustomForField?.(id);
                window.TripTransportActions?.routeFieldChanged?.();
            });
        });
        if (!unloadBound && typeof window.addEventListener === 'function') {
            unloadBound = true;
            window.addEventListener('beforeunload', event => {
                if (!window.TripPlanningDraft?.get?.()?.dirty) return;
                event.preventDefault();
                event.returnValue = '';
            });
        }
    }

    window.TripRouteForm = Object.freeze({ validationError, init });
    if (typeof document !== 'undefined' && document.readyState === 'loading' && document.addEventListener) {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else if (typeof document !== 'undefined') init();
})();
