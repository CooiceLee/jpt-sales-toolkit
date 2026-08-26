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
    const isTeam = plan?.planning_mode === 'team';
    window.TripTeamMap?.renderToolbar?.(plan);
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
        if (!isTeam) {
            addPoint(plan.origin_lat, plan.origin_lng,
                plan.origin_name || I18n.t('Origin'), '#2b6cb0');
        }
        const stops = isTeam
            ? window.TripTeamMap.visibleStops(plan) : (plan.stops || []);
        stops.filter(Boolean).forEach(stop => {
            const location = window.TripVisitState?.visitLocation?.(stop) || stop;
            const point = MapSupport.coordinatePair(location.lat, location.lng);
            if (!point) return;
            routePoints.push(point);
            bounds.push(point);
            const isFree = stop.stop_kind === 'free';
            const label = location.name || stop.location_name || stop.customer_name || I18n.t('Stop');
            const address = [location.address, location.city, location.postal_code, location.country]
                .filter(Boolean).join(', ');
            const marker = L.circleMarker(point, {
                radius: isFree ? 8 : 6,
                color: '#ffffff', weight: 2,
                fillColor: isFree ? '#d97706' : '#1f5135', fillOpacity: 0.95,
            }).bindTooltip(escapeHtml(`${stop.sequence_no || ''}. ${label}${address ? ` · ${address}` : ''}${
                isFree ? ` · ${I18n.t('Personal stop')}` : ''
            }`)).addTo(State.tripMapLayer);
            // A customer visit carries its date on the map: the point of the map
            // is to see when the trip reaches each customer, not just where.
            const when = scheduleBadge(stop);
            if (!isFree && when) {
                marker.bindTooltip(
                    `<b>${escapeHtml(String(stop.sequence_no || ''))}</b> ${escapeHtml(when)}`,
                    { permanent: true, direction: 'top', offset: [0, -8],
                      className: 'trip-map-when', opacity: 1 }
                );
            }
        });
        if (!isTeam) {
            addPoint(plan.destination_lat, plan.destination_lng,
                plan.destination_name || I18n.t('Destination'), '#7c3aed');
        }
        // A team plan has one route per member, so a single line through the
        // stops in order would be a path nobody travels. The journeys the
        // calculation produced are drawn instead, and nothing else is.
        if (isTeam) {
            window.TripTeamMap.draw(plan, State.tripMapLayer, bounds);
        } else if (routePoints.length >= 2) {
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
    State.tripMap?.setView(pair, 7);
};
