/** Editable stop schedule preferences backed by the trip-stop single source. */
(function() {
    const PERIODS = Object.freeze(['auto', 'AM', 'PM']);
    const CONFIRMATIONS = Object.freeze([
        'unconfirmed', 'tentative', 'confirmed', 'needs_reconfirmation', 'cancelled',
    ]);
    const h = value => escapeHtml(value ?? '');

    function option(value, selected, label) {
        return `<option value="${h(value)}" ${value === selected ? 'selected' : ''}>${h(I18n.t(label))}</option>`;
    }

    function render(stop) {
        const id = h(stop.id);
        const period = PERIODS.includes(stop.preferred_period) ? stop.preferred_period : 'auto';
        const confirmation = CONFIRMATIONS.includes(stop.confirmation_status)
            ? stop.confirmation_status : 'unconfirmed';
        const routeMode = window.TripPlanningDraft?.get?.()?.routeOrderMode
            || State.currentTripPlan?.route_order_mode;
        const canLock = Boolean(stop.planned_date && routeMode === 'manual');
        const lockHint = canLock
            ? 'Keep this visit at its current time when updating the route.'
            : 'Plan a date and choose Manual order to lock this visit.';
        return `<div class="trip-stop-schedule-controls">
            <label class="trip-field-label"><span>${h(I18n.t('Preferred period'))}</span>
                <select class="form-input" id="stop-period-${id}" onchange="TripTransportActions.schedulePreferenceChanged('${id}')">
                    ${option('auto', period, 'Automatic')}${option('AM', period, 'Morning (AM)')}${option('PM', period, 'Afternoon (PM)')}
                </select></label>
            <label class="trip-field-label"><span>${h(I18n.t('Confirmation status'))}</span>
                <select class="form-input" id="stop-confirmation-${id}">
                    ${option('unconfirmed', confirmation, 'Unconfirmed')}${option('tentative', confirmation, 'Tentative')}
                    ${option('confirmed', confirmation, 'Confirmed')}${option('needs_reconfirmation', confirmation, 'Needs reconfirmation')}
                    ${option('cancelled', confirmation, 'Cancelled')}
                </select></label>
            <label class="trip-check trip-schedule-lock" title="${h(I18n.t(lockHint))}">
                <input type="checkbox" id="stop-schedule-lock-${id}" onchange="TripTransportActions.schedulePreferenceChanged('${id}')" ${canLock && stop.schedule_locked ? 'checked' : ''} ${canLock ? '' : 'disabled'}>
                <span>${h(I18n.t('Lock saved schedule'))}</span>
            </label>
        </div>`;
    }

    function readPayload(stopId) {
        const period = document.getElementById(`stop-period-${stopId}`)?.value || 'auto';
        const confirmation = document.getElementById(`stop-confirmation-${stopId}`)?.value || 'unconfirmed';
        const lock = document.getElementById(`stop-schedule-lock-${stopId}`);
        return {
            preferred_period: PERIODS.includes(period) ? period : 'auto',
            confirmation_status: CONFIRMATIONS.includes(confirmation) ? confirmation : 'unconfirmed',
            schedule_locked: Boolean(lock && !lock.disabled && lock.checked),
        };
    }

    window.TripStopScheduleControls = Object.freeze({ PERIODS, CONFIRMATIONS, render, readPayload });
})();
