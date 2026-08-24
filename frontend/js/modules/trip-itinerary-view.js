function renderCurrentTripPlan() {
    const container = document.getElementById('trip-current-plan');
    if (!container) return;
    const plan = State.currentTripPlan;
    if (!plan) {
        container.innerHTML = `<div class="empty-state compact">${escapeHtml(I18n.t('Create or select a plan'))}</div>`;
        return;
    }
    const stops = plan.stops || [];
    if (!stops.length) {
        container.innerHTML = `
            <div class="trip-current-title">${escapeHtml(plan.title)}</div>
            ${renderTripItinerarySummary(plan)}
            <div class="empty-state compact">${escapeHtml(I18n.t('No stops yet'))}</div>
        `;
        return;
    }
    container.innerHTML = `
        <div class="trip-current-title">${escapeHtml(plan.title)}</div>
        ${renderTripItinerarySummary(plan)}
        ${stops.map((stop, index) => renderTripStopCard(stop, index, stops.length)).join('')}
    `;
}

function renderTripStopCard(stop, index, total) {
    if (stop.stop_kind === 'free') return renderTripFreeStopCard(stop, index, total);
    return `<div class="trip-stop trip-stop-customer" data-stop-id="${escapeHtml(stop.id)}" data-stop-kind="customer">
                <div class="trip-stop-head">
                    <strong>${escapeHtml(stop.sequence_no)}. ${escapeHtml(stop.customer_name)}</strong>
                    <div class="trip-stop-actions">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="moveTripStop('${stop.id}', -1)" ${index === 0 ? 'disabled' : ''}>${escapeHtml(I18n.t('Up'))}</button>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="moveTripStop('${stop.id}', 1)" ${index === total - 1 ? 'disabled' : ''}>${escapeHtml(I18n.t('Down'))}</button>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="removeTripStop('${stop.id}')">${escapeHtml(I18n.t('Remove'))}</button>
                    </div>
                </div>
                <div class="trip-stop-meta">${escapeHtml([stop.city, stop.country, stop.lead_display_id].filter(Boolean).join(' · '))}</div>
                <div class="trip-stop-schedule">${escapeHtml(formatTripStopSchedule(stop))}</div>
                <div class="trip-date-row">
                    <input type="date" class="form-input" id="stop-date-${stop.id}" value="${escapeHtml(stop.planned_date || '')}" readonly title="${escapeHtml(I18n.t('Calculated by route preview'))}">
                    <label class="trip-field-label">
                        <span>${escapeHtml(I18n.t('Stop duration (days)'))}</span>
                        <input type="number" min="0.5" max="30" step="0.5" class="form-input" data-stop-duration-half-days id="stop-stay-${stop.id}" value="${escapeHtml(TripDuration.toDisplayDays(TripPlanningDraft.durationFor(stop.id, TripDuration.readStopDuration(stop))))}" placeholder="${escapeHtml(I18n.t('Duration days'))}" oninput="TripTransportActions.stayChanged('${stop.id}', this.value)">
                    </label>
                </div>
                ${TripStopScheduleControls.render(stop)}
                <input type="text" class="form-input" id="stop-purpose-${stop.id}" value="${escapeHtml(stop.visit_purpose || '')}" placeholder="${escapeHtml(I18n.t('Visit purpose'))}">
                <select class="form-input" id="stop-result-${stop.id}">
                    ${['Planned', 'Visited', 'Follow-up Needed', 'Skipped'].map(status =>
                        `<option value="${status}" ${stop.result_status === status ? 'selected' : ''}>${escapeHtml(I18n.t(status))}</option>`
                    ).join('')}
                </select>
                <textarea class="form-input" id="stop-notes-${stop.id}" rows="2" placeholder="${escapeHtml(I18n.t('Result notes'))}">${escapeHtml(stop.result_notes || '')}</textarea>
                <button type="button" class="btn btn-primary btn-sm" onclick="saveTripStopResult('${stop.id}')">${escapeHtml(I18n.t('Save visit details'))}</button>
            </div>`;
}

function renderTripFreeStopCard(stop, index, total) {
    const name = stop.location_name || stop.customer_name || I18n.t('Untitled');
    const category = I18n.t(({ rest: 'Rest', hotel: 'Hotel', airport: 'Airport', transit: 'Transit', meal: 'Meal' })[stop.category] || 'Other');
    const location = [stop.address, stop.city, stop.country].filter(Boolean).join(' · ');
    return `<div class="trip-stop trip-stop-free" data-stop-id="${escapeHtml(stop.id)}" data-stop-kind="free">
        <div class="trip-stop-head">
            <strong>${escapeHtml(stop.sequence_no)}. ${escapeHtml(name)}</strong>
            <span class="trip-stop-kind">${escapeHtml(category)} · ${escapeHtml(I18n.t('Personal stop'))}</span>
        </div>
        <div class="trip-stop-meta">${escapeHtml(location || I18n.t('Location confirmed by coordinates'))}</div>
        <div class="trip-stop-schedule">${escapeHtml(formatTripStopSchedule(stop))}</div>
        ${stop.visit_purpose ? `<div class="trip-free-stop-detail"><strong>${escapeHtml(I18n.t('Purpose'))}:</strong> ${escapeHtml(stop.visit_purpose)}</div>` : ''}
        ${stop.notes ? `<div class="trip-free-stop-detail"><strong>${escapeHtml(I18n.t('Notes'))}:</strong> ${escapeHtml(stop.notes)}</div>` : ''}
        <label class="trip-field-label"><span>${escapeHtml(I18n.t('Stop duration (days)'))}</span>
            <input type="number" min="0.5" max="30" step="0.5" class="form-input" data-stop-duration-half-days id="stop-stay-${escapeHtml(stop.id)}"
                value="${escapeHtml(TripDuration.toDisplayDays(TripPlanningDraft.durationFor(stop.id, TripDuration.readStopDuration(stop))))}"
                oninput="TripTransportActions.stayChanged('${stop.id}', this.value)"></label>
        ${TripStopScheduleControls.render(stop)}
        <div class="trip-stop-actions">
            <button type="button" class="btn btn-secondary btn-sm" onclick="moveTripStop('${stop.id}', -1)" ${index === 0 ? 'disabled' : ''}>${escapeHtml(I18n.t('Up'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="moveTripStop('${stop.id}', 1)" ${index === total - 1 ? 'disabled' : ''}>${escapeHtml(I18n.t('Down'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="TripFreeStopForm.open('${stop.id}')">${escapeHtml(I18n.t('Edit'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="TripFreeStopActions.archive('${stop.id}')">${escapeHtml(I18n.t('Remove'))}</button>
            <button type="button" class="btn btn-primary btn-sm" onclick="saveTripStopSchedule('${stop.id}')">${escapeHtml(I18n.t('Save schedule details'))}</button>
        </div>
    </div>`;
}

function refreshTripStopCard(plan, stopId) {
    const stops = plan?.stops || [];
    const index = stops.findIndex(stop => stop.id === stopId);
    const card = Array.from(document.querySelectorAll('.trip-stop[data-stop-id]'))
        .find(element => element.dataset.stopId === String(stopId));
    if (!card || index < 0) return renderCurrentTripPlan();
    card.outerHTML = renderTripStopCard(stops[index], index, stops.length);
}

function renderTripItinerarySummary(plan) {
    const summary = plan?.itinerary_summary;
    if (!summary) return '';
    const warnings = tripSummaryWarnings(plan, summary);
    const endPeriod = ['AM', 'PM'].includes(summary.calculated_end_period)
        ? summary.calculated_end_period : '';
    const calculatedEnd = [summary.calculated_end_date, endPeriod].filter(Boolean).join(' · ') || '-';
    return `
        <div class="trip-itinerary-summary ${warnings.length ? 'has-warning' : ''}">
            <div><span>${escapeHtml(I18n.t(plan.itinerary_preview || summary.preview ? 'Preview end' : 'End'))}</span><strong>${escapeHtml(calculatedEnd)}</strong></div>
            <div><span>${escapeHtml(I18n.t('Business days'))}</span><strong>${escapeHtml(summary.total_business_days ?? '-')}</strong></div>
            <div><span>${escapeHtml(I18n.t('Stay'))}</span><strong>${escapeHtml(I18n.t('{count} days', { count: summary.total_stay_days ?? 0 }))}</strong></div>
            <div><span>${escapeHtml(I18n.t('Travel'))}</span><strong>${escapeHtml(I18n.t('{count} days', { count: summary.total_travel_days ?? 0 }))}</strong></div>
            <div><span>${escapeHtml(I18n.t('Distance'))}</span><strong>${escapeHtml(I18n.t('{count} km', { count: summary.total_distance_km ?? 0 }))}</strong></div>
            ${warnings.length ? `
                <div class="trip-itinerary-warning" role="alert">
                    <strong>${escapeHtml(I18n.t('Route needs attention'))}</strong>
                    <ul>${warnings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
                </div>` : ''}
        </div>
    `;
}

function tripSummaryWarnings(plan, summary) {
    const warnings = (summary.warnings || []).map(TripCandidateState.warningText);
    const overrunDays = Number(
        summary.overrun_days ?? summary.end_date_overrun_days ?? summary.exceeds_end_date_by_days ?? 0
    );
    const isOverrun = overrunDays > 0
        || summary.exceeds_end_date === true
        || summary.within_date_window === false;
    if (isOverrun) {
        warnings.unshift(overrunDays > 0
            ? I18n.t('The route exceeds the plan end date by {count} days. Shorten stays, remove stops, or extend the date range.', { count: overrunDays })
            : I18n.t('The route exceeds the plan end date. Shorten stays, remove stops, or extend the date range.'));
    }
    if ((summary.stale || summary.itinerary_stale || plan.itinerary_stale) && !warnings.length) {
        warnings.unshift(I18n.t('This route is out of date. Recalculate the preview before saving or exporting.'));
    }
    return [...new Set(warnings.filter(Boolean))];
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

window.refreshTripStopCard = refreshTripStopCard;
