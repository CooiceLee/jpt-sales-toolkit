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
        // A time the customer agreed to is a fact the plan is built around, so it
        // is typed in here rather than read back from whatever the last route
        // calculation happened to choose.
        const agreedPeriod = stop.planned_start_period === 'PM' ? 'PM' : 'AM';
        // Always usable: making it wait for the date to be saved first meant
        // typing a date, waiting, and coming back to tick a box that had been
        // greyed out - which reads as a box that cannot be ticked at all.
        const lockHint = stop.planned_date
            ? 'The customer agreed this time. The route will be planned around it.'
            : 'Enter the agreed date, then confirm it here.';
        return `<div class="trip-stop-schedule-controls${
                stop.schedule_locked ? ' is-agreed' : ''}">
            ${stop.schedule_locked ? `<p class="trip-agreed-banner">${h(I18n.t(
                'Agreed with the customer: {date} {period}. The route is planned around it.',
                { date: stop.planned_date,
                  period: I18n.t(agreedPeriod === 'PM' ? 'Afternoon (PM)' : 'Morning (AM)') }
            ))}</p>` : ''}
            <label class="trip-field-label"><span>${h(I18n.t('Agreed visit date'))}</span>
                <input type="date" class="form-input" id="stop-agreed-date-${id}"
                    value="${h(stop.planned_date || '')}"
                    onchange="TripStopScheduleActions.appointmentChanged('${id}')"></label>
            <label class="trip-field-label"><span>${h(I18n.t('Agreed period'))}</span>
                <select class="form-input" id="stop-agreed-period-${id}"
                    onchange="TripStopScheduleActions.appointmentChanged('${id}')">
                    ${option('AM', agreedPeriod, 'Morning (AM)')}${option('PM', agreedPeriod, 'Afternoon (PM)')}
                </select></label>
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
                <input type="checkbox" id="stop-schedule-lock-${id}" onchange="TripStopScheduleActions.appointmentChanged('${id}')" ${stop.schedule_locked ? 'checked' : ''}>
                <span>${h(I18n.t('Customer confirmed this time'))}</span>
            </label>
        </div>`;
    }

    function readPayload(stopId) {
        const period = document.getElementById(`stop-period-${stopId}`)?.value || 'auto';
        const confirmation = document.getElementById(`stop-confirmation-${stopId}`)?.value || 'unconfirmed';
        const lock = document.getElementById(`stop-schedule-lock-${stopId}`);
        const agreedDate = document.getElementById(`stop-agreed-date-${stopId}`)?.value || null;
        const agreedPeriod = document.getElementById(`stop-agreed-period-${stopId}`)?.value;
        return {
            planned_date: agreedDate,
            // The period only means anything alongside a date.
            planned_start_period: agreedDate
                ? (agreedPeriod === 'PM' ? 'PM' : 'AM') : null,
            preferred_period: PERIODS.includes(period) ? period : 'auto',
            confirmation_status: CONFIRMATIONS.includes(confirmation) ? confirmation : 'unconfirmed',
            // Confirming a time means nothing without a date to confirm.
            schedule_locked: Boolean(agreedDate && lock && lock.checked),
        };
    }

    window.TripStopScheduleControls = Object.freeze({ PERIODS, CONFIRMATIONS, render, readPayload });
})();
