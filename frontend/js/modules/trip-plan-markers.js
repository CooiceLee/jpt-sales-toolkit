/** The plan itself on the map: its stops, its ends, and the lines between.
 *
 * Split out of renderTripMap when that file outgrew its module boundary. Each
 * marker is registered against the stop it stands for, so "show me this visit"
 * can find that visit rather than a coordinate several customers share.
 */
(function () {
    'use strict';

    function draw(bounds) {
        if (!State.tripMap || !State.tripMapLayer) return;
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
                }).addTo(State.tripMapLayer);
                // The name is what tells two dots apart, so it is what the marker
                // says. Binding the date over it - permanently, on every customer -
                // replaced every name with a number and left twenty-four labels
                // overlapping each other.
                const when = scheduleBadge(stop);
                marker.bindTooltip(escapeHtml(`${stop.sequence_no || ''}. ${label}${
                    when ? ` · ${when}` : ''}${address ? ` · ${address}` : ''}${
                    isFree ? ` · ${I18n.t('Personal stop')}` : ''}`));
                marker.bindPopup('');
                State.tripMapMarkers.set(`stop:${stop.id}`, {
                    kind: 'stop', id: stop.id, marker, point,
                    name: label, detail: stop.lead_display_id || '',
                    exact: !(stop.needs_coordinate_review
                        || (location.coordinate_quality && location.coordinate_quality !== 'exact')),
                });
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
    }

    window.TripPlanMarkers = Object.freeze({ draw });
})();
