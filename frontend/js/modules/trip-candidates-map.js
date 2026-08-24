function renderTripMap() {
    if (!State.tripMap || !State.tripMapLayer) return;
    State.tripMapLayer.clearLayers();
    const bounds = [];
    const selectedCustomerIds = new Set(
        (State.currentTripPlan?.stops || []).filter(stop => stop?.stop_kind !== 'free').map(stop => stop.customer_id)
    );

    (State.tripCandidates || []).forEach((candidate, index) => {
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
        const candidateAction = hasExactCoordinates
            ? `<button type="button" class="btn btn-primary btn-sm" onclick="addCandidateToCurrentPlan(${index})">${escapeHtml(I18n.t('Add to Plan'))}</button>`
            : `<div class="trip-coordinate-required">${escapeHtml(I18n.t('Precise coordinates are required before this customer can be added.'))}</div>
                <div class="trip-popup-actions">
                    <button type="button" class="btn btn-primary btn-sm" disabled>${escapeHtml(I18n.t('Add to Plan'))}</button>
                    <button type="button" class="btn btn-secondary btn-sm" onclick="openTripCandidateCoordinateReview(${index})">${escapeHtml(I18n.t('Open Coordinate Review'))}</button>
                </div>`;
        marker.bindPopup(`
            <div class="map-popup">
                <div class="map-popup-title">${escapeHtml(candidate.customer_name)}</div>
                <div class="map-popup-meta">${escapeHtml([candidate.city, candidate.country].filter(Boolean).join(', '))}</div>
                <div class="map-popup-stats">
                    <span>${escapeHtml(I18n.t('{count} open', { count: Number(candidate.open_count) || 0 }))}</span>
                    <span>${escapeHtml(formatMoney(candidate.pipeline_value || 0))}</span>
                </div>
                ${candidateAction}
            </div>
        `);
        marker.addTo(State.tripMapLayer);
        bounds.push(pair);
    });

    const plan = State.currentTripPlan;
    if (plan?.stops?.length) {
        const routePoints = [];
        const addPoint = (lat, lng, label, color) => {
            const point = MapSupport.coordinatePair(lat, lng);
            if (!point) return;
            routePoints.push(point);
            bounds.push(point);
            L.circleMarker(point, {
                radius: 7,
                color: '#ffffff',
                weight: 2,
                fillColor: color,
                fillOpacity: 0.95
            }).bindTooltip(escapeHtml(label)).addTo(State.tripMapLayer);
        };
        addPoint(plan.origin_lat, plan.origin_lng, plan.origin_name || I18n.t('Origin'), '#2b6cb0');
        (plan.stops || []).filter(Boolean).forEach(stop => {
            const location = window.TripVisitState?.visitLocation?.(stop) || stop;
            const point = MapSupport.coordinatePair(location.lat, location.lng);
            if (!point) return;
            routePoints.push(point);
            bounds.push(point);
            const isFree = stop.stop_kind === 'free';
            const label = location.name || stop.location_name || stop.customer_name || I18n.t('Stop');
            const address = [location.address, location.city, location.postal_code, location.country]
                .filter(Boolean).join(', ');
            L.circleMarker(point, {
                radius: isFree ? 8 : 6,
                color: '#ffffff', weight: 2,
                fillColor: isFree ? '#d97706' : '#1f5135', fillOpacity: 0.95,
            }).bindTooltip(escapeHtml(`${stop.sequence_no || ''}. ${label}${address ? ` · ${address}` : ''}${
                isFree ? ` · ${I18n.t('Personal stop')}` : ''
            }`)).addTo(State.tripMapLayer);
        });
        addPoint(plan.destination_lat, plan.destination_lng, plan.destination_name || I18n.t('Destination'), '#7c3aed');
        if (routePoints.length >= 2) {
            L.polyline(routePoints, {
                color: '#1f5135',
                weight: 3,
                opacity: 0.72,
                dashArray: '8 6'
            }).addTo(State.tripMapLayer);
        }
    }

    if (bounds.length) {
        State.tripMap.fitBounds(bounds, { padding: [24, 24], maxZoom: 6 });
    }
}

window.focusTripCandidate = function(index) {
    const item = State.tripCandidates[index];
    const pair = MapSupport.coordinatePair(item?.lat, item?.lng);
    if (!pair) {
        alert(I18n.t('This customer needs coordinate review before it can be shown on the map.'));
        return;
    }
    State.tripMap?.setView(pair, 7);
};
