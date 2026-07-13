function renderCurrentTripPlan() {
    const container = document.getElementById('trip-current-plan');
    if (!container) return;
    const plan = State.currentTripPlan;
    if (!plan) {
        container.innerHTML = '<div class="empty-state compact">Create or select a plan</div>';
        return;
    }
    const stops = plan.stops || [];
    if (!stops.length) {
        container.innerHTML = `
            <div class="trip-current-title">${escapeHtml(plan.title)}</div>
            ${renderTripItinerarySummary(plan)}
            <div class="empty-state compact">No stops yet</div>
        `;
        return;
    }
    container.innerHTML = `
        <div class="trip-current-title">${escapeHtml(plan.title)}</div>
        ${renderTripItinerarySummary(plan)}
        ${stops.map((stop, index) => `
            <div class="trip-stop" data-stop-id="${stop.id}">
                <div class="trip-stop-head">
                    <strong>${escapeHtml(stop.sequence_no)}. ${escapeHtml(stop.customer_name)}</strong>
                    <div class="trip-stop-actions">
                        <button type="button" class="btn btn-secondary btn-sm" onclick="moveTripStop('${stop.id}', -1)" ${index === 0 ? 'disabled' : ''}>Up</button>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="moveTripStop('${stop.id}', 1)" ${index === stops.length - 1 ? 'disabled' : ''}>Down</button>
                        <button type="button" class="btn btn-secondary btn-sm" onclick="removeTripStop('${stop.id}')">Remove</button>
                    </div>
                </div>
                <div class="trip-stop-meta">${escapeHtml([stop.city, stop.country, stop.lead_display_id].filter(Boolean).join(' · '))}</div>
                <div class="trip-stop-schedule">${escapeHtml(formatTripStopSchedule(stop))}</div>
                <div class="trip-date-row">
                    <input type="date" class="form-input" id="stop-date-${stop.id}" value="${escapeHtml(stop.planned_date || '')}">
                    <input type="number" min="1" max="30" class="form-input" id="stop-stay-${stop.id}" value="${escapeHtml(stop.stay_days || 1)}" placeholder="Stay days">
                </div>
                <input type="text" class="form-input" id="stop-purpose-${stop.id}" value="${escapeHtml(stop.visit_purpose || '')}" placeholder="Visit purpose">
                <select class="form-input" id="stop-result-${stop.id}">
                    ${['Planned', 'Visited', 'Follow-up Needed', 'Skipped'].map(status =>
                        `<option value="${status}" ${stop.result_status === status ? 'selected' : ''}>${status}</option>`
                    ).join('')}
                </select>
                <textarea class="form-input" id="stop-notes-${stop.id}" rows="2" placeholder="Result notes">${escapeHtml(stop.result_notes || '')}</textarea>
                <button type="button" class="btn btn-primary btn-sm" onclick="saveTripStopResult('${stop.id}')">Save stop</button>
            </div>
        `).join('')}
    `;
}

function renderTripItinerarySummary(plan) {
    const summary = plan?.itinerary_summary;
    if (!summary) return '';
    const warnings = summary.warnings || [];
    return `
        <div class="trip-itinerary-summary">
            <div><span>${plan.itinerary_preview || summary.preview ? 'Preview end' : 'End'}</span><strong>${escapeHtml(summary.calculated_end_date || '-')}</strong></div>
            <div><span>Business days</span><strong>${escapeHtml(summary.total_business_days || '-')}</strong></div>
            <div><span>Travel</span><strong>${escapeHtml(summary.total_travel_days || 0)} days</strong></div>
            <div><span>Distance</span><strong>${escapeHtml(summary.total_distance_km || 0)} km</strong></div>
            ${warnings.length ? `<div class="trip-itinerary-warning">${escapeHtml(warnings.join(' '))}</div>` : ''}
        </div>
    `;
}

function formatTripStopSchedule(stop) {
    const dates = [stop.planned_date, stop.planned_end_date].filter(Boolean).join(' to ');
    const travel = stop.travel_from_label
        ? `From ${stop.travel_from_label}: ${stop.travel_mode || '-'}, ${stop.travel_distance_km || 0} km, ${stop.travel_time_hours || 0}h`
        : '';
    return [dates, travel].filter(Boolean).join(' · ') || 'Not scheduled';
}

