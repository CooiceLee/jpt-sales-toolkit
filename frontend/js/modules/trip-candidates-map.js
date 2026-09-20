function renderTripMap() {
    if (!State.tripMap || !State.tripMapLayer) return;
    State.tripMapLayer.clearLayers();
    // Which marker stands for which business object. Without it a map request
    // can only move the view to a coordinate and hope the reader works out
    // which of the dots there was meant.
    State.tripMapMarkers = new Map();
    const bounds = [];
    const selectedCustomerIds = new Set(
        (State.currentTripPlan?.stops || []).filter(stop => stop?.stop_kind !== 'free').map(stop => stop.customer_id)
    );

    // One member's journey is what the map is showing: customers who are only
    // candidates for this trip are not part of it. Drawn in the same green as
    // the stops, they read as that member's own - a map with dots and no line
    // between them, when in fact none of those dots are theirs.
    const soloMember = State.currentTripPlan?.planning_mode === 'team'
        && (window.TripTeamMap?.view?.() || 'all') !== 'all';
    (State.tripCandidates || []).forEach((candidate, index) => {
        if (soloMember) return;
        const pair = MapSupport.coordinatePair(candidate?.lat, candidate?.lng);
        if (!pair) return;
        const selected = selectedCustomerIds.has(candidate.customer_id);
        const marker = L.circleMarker(pair, {
            radius: selected ? 13 : Math.min(20, 7 + (candidate.open_count || 0) * 3),
            color: selected ? '#1f5135' : '#ffffff',
            weight: selected ? 3 : 2,
            fillColor: selected ? '#2f855a' : (candidate.needs_coordinate_review ? '#D98C24' : '#8B1E3F'),
            fillOpacity: 0.86,
            dashArray: candidate.needs_coordinate_review ? '4 3' : null
        });

        marker.bindTooltip(escapeHtml(
            `${candidate.customer_name || ''} · ${Number(candidate.score) || 0}`
        ));
        const hasExactCoordinates = window.TripCandidateState?.hasExactCoordinates
            ? window.TripCandidateState.hasExactCoordinates(candidate)
            : Boolean(pair && candidate.coordinate_quality === 'exact' && !candidate.needs_coordinate_review);
        // The same customer must not read as addable here and already added in
        // the list beside it.
        const alreadyOnPlan = selected;
        const candidateAction = alreadyOnPlan
            ? `<button type="button" class="btn btn-secondary btn-sm" disabled>${escapeHtml(I18n.t('Already added'))}</button>`
            : hasExactCoordinates
            ? `<button type="button" class="btn btn-primary btn-sm" onclick="addCandidateToCurrentPlan(${index})">${escapeHtml(I18n.t('Add to plan'))}</button>`
            : `<div class="trip-coordinate-required">${escapeHtml(I18n.t('Precise coordinates are required before this customer can be added.'))}</div>
                <div class="trip-popup-actions">
                    <button type="button" class="btn btn-primary btn-sm" disabled>${escapeHtml(I18n.t('Add to plan'))}</button>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openTripCandidateCoordinateReview(${index})">${escapeHtml(I18n.t('Open Coordinate Review'))}</button>
                </div>`;
        State.tripMapMarkers.set(`candidate:${candidate.customer_id}`, {
            kind: 'candidate', id: candidate.customer_id, marker, point: pair,
            name: candidate.customer_name, detail: candidate.primary_lead_display_id || '',
            exact: hasExactCoordinates,
        });
        marker.bindPopup(`
            <div class="map-popup">
                <div class="map-popup-title" data-business>${escapeHtml(candidate.customer_name)}</div>
                <div class="map-popup-meta">${escapeHtml([candidate.city, candidate.country].filter(Boolean).join(', '))}</div>
                <div class="map-popup-stats">
                    <span>${escapeHtml(I18n.t('{count} open', { count: Number(candidate.open_count) || 0 }))}</span>
                    <span>${escapeHtml(MoneyTotals.text(candidate.pipeline_value_by_currency))}</span>
                </div>
                ${candidateAction}
            </div>
        `);
        marker.addTo(State.tripMapLayer);
        bounds.push(pair);
    });

    window.TripPlanMarkers?.draw?.(bounds);

    // Somebody asked for one object a moment ago; fitting the whole trip back
    // into view would undo that, so the request is restored instead.
    if (window.TripMapFocus?.restore?.()) return;
    if (bounds.length) {
        State.tripMap.fitBounds(bounds, { padding: [24, 24], maxZoom: 6 });
    }
}

function scheduleBadge(stop) {
    const short = value => {
        const text = String(value || '');
        return text.length >= 10 ? text.slice(5) : text;
    };
    const start = short(stop.planned_date);
    if (!start) return '';
    const end = short(stop.planned_end_date);
    if (end && end !== start) return `${start}→${end}`;
    const period = stop.planned_start_period === stop.planned_end_period
        ? stop.planned_start_period : '';
    return period ? `${start} ${period}` : start;
}

window.focusTripCandidate = function(index) {
    const item = State.tripCandidates[index];
    const pair = MapSupport.coordinatePair(item?.lat, item?.lng);
    if (!pair) {
        alert(I18n.t('This customer needs coordinate review before it can be shown on the map.'));
        return;
    }
    // Bring the map into view, emphasise this customer and open their own
    // information box - not just move the centre of a map nobody can see.
    if (window.TripMapFocus?.show?.('candidate', item.customer_id)) return;
    State.tripMap?.setView(pair, 7);
};
