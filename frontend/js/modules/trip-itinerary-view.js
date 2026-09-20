/** What is drawn when the plan changes: the plan's own line, the reorder list,
 *  and the panel for whatever is selected on the timeline.
 *
 * The name stays renderCurrentTripPlan because every path that changes a plan
 * calls it - a save, a preview, a member joining, a stop removed elsewhere. It
 * used to draw a column of open forms; it now draws the one form the reader
 * asked for, which is what "the current plan on screen" has come to mean.
 */
function renderCurrentTripPlan() {
    const plan = State.currentTripPlan;
    window.TripZones?.renderHeader?.(plan);
    window.TripBriefingPicker?.render?.();   // same plan, drawn from one place
    renderTripPlanHeadline(plan);
    window.TripStopOrderView?.render?.(plan);
    const container = document.getElementById('trip-current-plan');
    if (!container) return;
    container.innerHTML = window.TripDetailPanel?.render?.(plan)
        || `<div class="empty-state compact">${escapeHtml(I18n.t('Create or select a plan'))}</div>`;
}

function renderTripPlanHeadline(plan) {
    const headline = document.getElementById('trip-plan-headline');
    if (!headline) return false;
    headline.innerHTML = plan
        ? `<div class="trip-current-title" data-business>${escapeHtml(plan.title)}</div>
            ${renderTripItinerarySummary(plan)}`
        : '';
    return true;
}

/** One stop's form redrawn in place, without disturbing anything else.
 *
 * Including what has been typed into it and not saved: the card is rebuilt from
 * the server's answer, so a visit purpose entered a moment before an agreed
 * time saved itself would otherwise be replaced by the stored value.
 */
function refreshTripStopCard(plan, stopId) {
    const stops = plan?.stops || [];
    const index = stops.findIndex(stop => stop.id === stopId);
    const card = Array.from(document.querySelectorAll('#trip-current-plan .trip-stop[data-stop-id]'))
        .find(element => element.dataset.stopId === String(stopId));
    if (!card || index < 0) return renderCurrentTripPlan();
    card.outerHTML = renderTripStopCard(stops[index], index, stops.length);
    // The purpose is drawn from its own draft (trip-stop-typing.js), so the
    // rebuild carries it without reading the old field - and a field nobody
    // touched takes the value the server just sent.
    window.TripStopTyping?.restore?.(stopId);
    window.TripStopOrderView?.render?.(plan);
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
            <div><span>${escapeHtml(I18n.t(
                (plan?.members || []).length > 1 ? 'Team aggregate distance' : 'Distance'
            ))}</span><strong>${escapeHtml(I18n.t('{count} km', { count: summary.total_distance_km ?? 0 }))}</strong></div>
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

window.refreshTripStopCard = refreshTripStopCard;
