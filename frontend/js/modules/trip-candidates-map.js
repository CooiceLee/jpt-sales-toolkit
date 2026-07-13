function renderTripMap() {
    if (!State.tripMap || !State.tripMapLayer) return;
    State.tripMapLayer.clearLayers();
    const bounds = [];
    const selectedCustomerIds = new Set((State.currentTripPlan?.stops || []).map(stop => stop.customer_id));

    (State.tripCandidates || []).forEach((candidate, index) => {
        if (!Number.isFinite(Number(candidate.lat)) || !Number.isFinite(Number(candidate.lng))) return;
        const selected = selectedCustomerIds.has(candidate.customer_id);
        const marker = L.circleMarker([candidate.lat, candidate.lng], {
            radius: selected ? 13 : Math.min(20, 7 + (candidate.open_count || 0) * 3),
            color: selected ? '#1f5135' : '#ffffff',
            weight: selected ? 3 : 2,
            fillColor: selected ? '#2f855a' : (candidate.needs_coordinate_review ? '#D98C24' : '#8B1E3F'),
            fillOpacity: 0.86,
            dashArray: candidate.needs_coordinate_review ? '4 3' : null
        });
        marker.bindTooltip(`${candidate.customer_name} · ${candidate.score}`);
        marker.bindPopup(`
            <div class="map-popup">
                <div class="map-popup-title">${escapeHtml(candidate.customer_name)}</div>
                <div class="map-popup-meta">${escapeHtml([candidate.city, candidate.country].filter(Boolean).join(', '))}</div>
                <div class="map-popup-stats">
                    <span>${candidate.open_count || 0} open</span>
                    <span>${formatMoney(candidate.pipeline_value || 0)}</span>
                </div>
                <button type="button" class="btn btn-primary btn-sm" onclick="addCandidateToCurrentPlan(${index})">Add to Plan</button>
            </div>
        `);
        marker.addTo(State.tripMapLayer);
        bounds.push([candidate.lat, candidate.lng]);
    });

    const plan = State.currentTripPlan;
    if (plan?.stops?.length) {
        const routePoints = [];
        const addPoint = (lat, lng, label, color) => {
            if (!Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) return;
            const point = [Number(lat), Number(lng)];
            routePoints.push(point);
            bounds.push(point);
            L.circleMarker(point, {
                radius: 7,
                color: '#ffffff',
                weight: 2,
                fillColor: color,
                fillOpacity: 0.95
            }).bindTooltip(label).addTo(State.tripMapLayer);
        };
        addPoint(plan.origin_lat, plan.origin_lng, plan.origin_name || 'Origin', '#2b6cb0');
        (plan.stops || []).forEach(stop => {
            if (Number.isFinite(Number(stop.lat)) && Number.isFinite(Number(stop.lng))) {
                const point = [Number(stop.lat), Number(stop.lng)];
                routePoints.push(point);
                bounds.push(point);
            }
        });
        addPoint(plan.destination_lat, plan.destination_lng, plan.destination_name || 'Destination', '#7c3aed');
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
    if (!item || !Number.isFinite(Number(item.lat)) || !Number.isFinite(Number(item.lng))) {
        alert('This customer needs coordinate review before it can be shown on the map.');
        return;
    }
    State.tripMap?.setView([item.lat, item.lng], 7);
};

