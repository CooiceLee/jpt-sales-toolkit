/** One stop's form: the same fields it always had, for the stop that is open.
 *
 * Twenty stops were twenty of these stacked in a column. Which one is on screen
 * is now the reader's choice on the timeline, so the card no longer folds -
 * there is one of it, and it is the one they asked for.
 */
const TRIP_TIMING_LABELS = Object.freeze({
    agreed: 'Time agreed with the customer',
    flexible: 'Time can still be moved',
    unscheduled: 'No date yet',
});

function tripStopTiming(stop) {
    if (window.TripStopBoard?.timing) return window.TripStopBoard.timing(stop);
    if (stop.schedule_locked) return 'agreed';
    return stop.planned_date ? 'flexible' : 'unscheduled';
}

function tripStopFlag(stop) {
    const timing = tripStopTiming(stop);
    return `<span class="trip-stop-flag is-${timing}">${
        escapeHtml(I18n.t(TRIP_TIMING_LABELS[timing]))}</span>`;
}

// Up and Down move this stop in the plan; the same pair drives the deliberate
// "reorder stops" list, and neither is a way of sorting what is read.
function tripStopHead(stop, index, total, remove) {
    const name = stop.stop_kind === 'free'
        ? (stop.location_name || stop.customer_name || I18n.t('Untitled'))
        : stop.customer_name;
    return `<div class="trip-stop-head">
            <strong data-business>${escapeHtml(stop.sequence_no)}. ${escapeHtml(name)}</strong>
            <div class="trip-stop-actions">
                <button type="button" class="btn btn-secondary btn-sm" data-move="up" onclick="moveTripStop('${stop.id}', -1)" ${index === 0 ? 'disabled' : ''}>${escapeHtml(I18n.t('Up'))}</button>
                <button type="button" class="btn btn-secondary btn-sm" data-move="down" onclick="moveTripStop('${stop.id}', 1)" ${index === total - 1 ? 'disabled' : ''}>${escapeHtml(I18n.t('Down'))}</button>
                ${remove}
            </div>
        </div>`;
}

/** Both versions, when the stored purpose moved while this one was typed. */
function tripStopPurposeConflict(stop) {
    const clash = window.TripStopTyping?.conflict?.(stop.id);
    if (!clash) return '';
    return `<div class="trip-purpose-conflict" role="alert">
        <strong>${escapeHtml(I18n.t('This visit purpose was changed elsewhere while you were editing.'))}</strong>
        <dl class="trip-detail-facts">
            <div><dt>${escapeHtml(I18n.t('Theirs'))}</dt><dd data-business>${escapeHtml(clash.theirs || '-')}</dd></div>
            <div><dt>${escapeHtml(I18n.t('Mine'))}</dt><dd data-business>${escapeHtml(clash.mine || '-')}</dd></div>
        </dl>
        <div class="trip-action-row">
            <button type="button" class="btn btn-secondary btn-sm"
                onclick="TripStopTyping.keepMine('${stop.id}')">${escapeHtml(I18n.t('Keep mine and overwrite'))}</button>
            <button type="button" class="btn btn-secondary btn-sm"
                onclick="TripStopTyping.takeTheirs('${stop.id}')">${escapeHtml(I18n.t('Use the newer version'))}</button>
        </div>
    </div>`;
}

function renderTripStopCard(stop, index, total) {
    if (stop.stop_kind === 'free') return renderTripFreeStopCard(stop, index, total);
    const id = escapeHtml(stop.id);
    const remove = `<button type="button" class="btn btn-secondary btn-sm" onclick="removeTripStop('${stop.id}')">${escapeHtml(I18n.t('Remove'))}</button>`;
    return `<div class="trip-stop trip-stop-customer is-open" data-stop-id="${id}" data-stop-kind="customer" data-stop-timing="${tripStopTiming(stop)}">
                ${tripStopHead(stop, index, total, remove)}
                <div class="trip-stop-meta">${tripStopFlag(stop)}<span data-business>${escapeHtml([stop.city, stop.country, stop.lead_display_id].filter(Boolean).join(' · '))}</span></div>
                <div class="trip-stop-schedule">${escapeHtml(formatTripStopSchedule(stop))}${
                    window.TripStopPending?.half?.(stop) ? `</div><div class="trip-stop-pending">${escapeHtml(
                        I18n.t('Last calculated result. Waiting to be updated: {count} days.', {
                            count: TripDuration.toDisplayDays(window.TripStopPending.half(stop)) }))}` : ''}</div>
                <div class="trip-stop-body" id="stop-body-${id}">
                <div class="trip-date-row">
                    <label class="trip-field-label">
                        <span>${escapeHtml(I18n.t('Stop duration (days)'))}</span>
                        <input type="number" min="0.5" max="30" step="0.5" class="form-input" data-stop-duration-half-days id="stop-stay-${stop.id}" value="${escapeHtml(TripDuration.toDisplayDays(TripPlanningDraft.durationFor(stop.id, TripDuration.readStopDuration(stop))))}" placeholder="${escapeHtml(I18n.t('Duration days'))}" oninput="TripTransportActions.stayChanged('${stop.id}', this.value)">
                    </label>
                    <p class="trip-form-help">${escapeHtml(I18n.t('Calculate and save the route to apply a new duration.'))}</p>
                </div>
                ${TripStopScheduleControls.render(stop)}
                <label class="trip-field-label"><span>${escapeHtml(I18n.t('Visit purpose'))}</span>
                    <input type="text" class="form-input" id="stop-purpose-${stop.id}"
                        value="${escapeHtml(window.TripStopTyping?.valueFor?.(stop.id, stop.visit_purpose || '')
                            ?? (stop.visit_purpose || ''))}"
                        oninput="TripStopTyping.note('${stop.id}', this.value)"
                        placeholder="${escapeHtml(I18n.t('Visit purpose'))}"></label>
                ${tripStopPurposeConflict(stop)}
                <div class="trip-action-row">
                    <button type="button" class="btn btn-primary btn-sm" onclick="saveTripStopResult('${stop.id}')">${escapeHtml(I18n.t('Save visit details'))}</button>
                    ${window.TripStopTyping?.isDirty?.(stop.id) ? `<button type="button" class="btn btn-secondary btn-sm"
                        onclick="TripStopTyping.discard('${stop.id}')">${escapeHtml(I18n.t('Discard the unsaved purpose'))}</button>` : ''}
                </div>
                <div class="trip-stop-result">
                    <dl class="trip-detail-facts">
                        <div><dt>${escapeHtml(I18n.t('Result'))}</dt><dd>${escapeHtml(I18n.t(stop.result_status || 'Planned'))}</dd></div>
                        <div><dt>${escapeHtml(I18n.t('Actually visited'))}</dt><dd>${escapeHtml(
                            window.TripStopTimes?.visited?.(stop) || I18n.t('Not recorded yet'))}</dd></div>
                        ${stop.result_notes ? `<div><dt>${escapeHtml(I18n.t('Result notes'))}</dt><dd data-business>${escapeHtml(stop.result_notes)}</dd></div>` : ''}
                    </dl>
                    <button type="button" class="btn btn-secondary btn-sm"
                        onclick="TripRouteFocus.goToVisitRecord('${stop.id}')">${escapeHtml(I18n.t('Record the actual visit'))}</button>
                </div>
                </div>
            </div>`;
}

const WAYPOINT_CATEGORIES = ['airport', 'transit'];

function renderTripFreeStopCard(stop, index, total) {
    const id = escapeHtml(stop.id);
    const category = I18n.t(({ rest: 'Rest', hotel: 'Hotel', airport: 'Airport', transit: 'Transit', meal: 'Meal' })[stop.category] || 'Other');
    const location = [stop.address, stop.city, stop.country].filter(Boolean).join(' · ');
    const remove = `<button type="button" class="btn btn-secondary btn-sm" onclick="TripFreeStopActions.archive('${stop.id}')">${escapeHtml(I18n.t('Remove'))}</button>`;
    return `<div class="trip-stop trip-stop-free is-open" data-stop-id="${id}" data-stop-kind="free" data-stop-timing="${tripStopTiming(stop)}">
        ${tripStopHead(stop, index, total, remove)}
        <div class="trip-stop-meta">${tripStopFlag(stop)}
            <span class="trip-stop-kind">${escapeHtml(category)} · ${escapeHtml(I18n.t('Personal stop'))}</span>
            <span data-business>${escapeHtml(location || I18n.t('Location confirmed by coordinates'))}</span>
        </div>
        <div class="trip-stop-schedule">${escapeHtml(formatTripStopSchedule(stop))}</div>
        <div class="trip-stop-body" id="stop-body-${id}">
        ${stop.visit_purpose ? `<div class="trip-free-stop-detail"><strong>${escapeHtml(I18n.t('Purpose'))}:</strong> ${escapeHtml(stop.visit_purpose)}</div>` : ''}
        ${stop.notes ? `<div class="trip-free-stop-detail"><strong>${escapeHtml(I18n.t('Notes'))}:</strong> ${escapeHtml(stop.notes)}</div>` : ''}
        ${WAYPOINT_CATEGORIES.includes(stop.category)
            ? `<div class="trip-stop-waypoint">${escapeHtml(I18n.t('Pass-through point. It joins the route without taking visit time.'))}</div>`
            : `<label class="trip-field-label"><span>${escapeHtml(I18n.t('Stop duration (days)'))}</span>
            <input type="number" min="0.5" max="30" step="0.5" class="form-input" data-stop-duration-half-days id="stop-stay-${escapeHtml(stop.id)}"
                value="${escapeHtml(TripDuration.toDisplayDays(TripPlanningDraft.durationFor(stop.id, TripDuration.readStopDuration(stop))))}"
                oninput="TripTransportActions.stayChanged('${stop.id}', this.value)"></label>`}
        ${TripStopScheduleControls.render(stop)}
        <div class="trip-stop-actions">
            <button type="button" class="btn btn-secondary btn-sm" onclick="TripFreeStopForm.open('${stop.id}')">${escapeHtml(I18n.t('Edit'))}</button>
            <button type="button" class="btn btn-primary btn-sm" onclick="saveTripStopSchedule('${stop.id}')">${escapeHtml(I18n.t('Save schedule details'))}</button>
        </div>
        </div>
    </div>`;
}

function formatTripStopSchedule(stop) {
    const start = [stop.planned_date, stop.planned_start_period].filter(Boolean).join(' ');
    const end = [stop.planned_end_date, stop.planned_end_period].filter(Boolean).join(' ');
    const dates = start && end && start !== end
        ? I18n.t('{start} to {end}', { start, end }) : start || end || '';
    const modeKey = ({ drive: 'Drive', flight: 'Flight', ground_public: 'Ground public', other: 'Other' })[
        String(stop.travel_mode || '').toLowerCase()
    ] || stop.travel_mode || '-';
    const travel = stop.travel_from_label
        ? I18n.t('From {location}: {mode}, {distance} km, {hours}h', {
            location: stop.travel_from_label, mode: I18n.t(modeKey),
            distance: stop.travel_distance_km || 0, hours: stop.travel_time_hours || 0,
        })
        : '';
    return [dates, travel].filter(Boolean).join(' · ') || I18n.t('Not scheduled');
}

