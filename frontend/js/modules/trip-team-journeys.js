/** The journeys a team plan actually contains, ready to be drawn. */
(function() {
    const t = (key, params = {}) => I18n.t(key, params);

    function memberOf(plan, userId) {
        return (plan?.members || []).find(item => item.user_id === userId) || null;
    }

    function memberName(plan, userId) {
        return memberOf(plan, userId)?.display_name || userId || t('Unassigned');
    }

    /**
     * Where one end of a journey is.
     *
     * Looked up from the leg's own endpoint, never worked out from the order the
     * stops happen to be in: a leg the calculation did not produce must not be
     * possible to draw. Each member can leave from and return to their own
     * place, so the plan's endpoints are only the fallback.
     */
    function endpoint(plan, leg, side) {
        const stopId = leg[`${side}_stop_id`];
        if (stopId) {
            const stop = (plan?.stops || []).find(item => item.id === stopId);
            if (!stop) return null;
            const location = window.TripVisitState?.visitLocation?.(stop) || stop;
            return {
                lat: location.lat, lng: location.lng,
                label: location.name || stop.location_name || stop.customer_name,
            };
        }
        const member = memberOf(plan, leg.member_id);
        const kind = leg[`${side}_kind`];
        if (kind === 'origin') {
            return {
                lat: member?.origin_lat_override ?? plan?.origin_lat,
                lng: member?.origin_lng_override ?? plan?.origin_lng,
                label: member?.origin_name_override || plan?.origin_name,
            };
        }
        if (kind === 'destination') {
            return {
                lat: member?.destination_lat_override ?? plan?.destination_lat,
                lng: member?.destination_lng_override ?? plan?.destination_lng,
                label: member?.destination_name_override || plan?.destination_name,
            };
        }
        return null;
    }

    function pair(point) {
        return point && window.MapSupport?.coordinatePair
            ? MapSupport.coordinatePair(point.lat, point.lng) : null;
    }

    /** A flown leg goes through its airports, because that is where it goes. */
    function pointsOf(plan, leg) {
        const stops = [
            endpoint(plan, leg, 'from'),
            leg.departure_airport_lat != null
                ? { lat: leg.departure_airport_lat, lng: leg.departure_airport_lng,
                    label: leg.departure_airport_name } : null,
            leg.arrival_airport_lat != null
                ? { lat: leg.arrival_airport_lat, lng: leg.arrival_airport_lng,
                    label: leg.arrival_airport_name } : null,
            endpoint(plan, leg, 'to'),
        ].filter(Boolean);
        const points = stops.map(pair);
        return points.some(item => !item) ? [] : points;
    }

    // The same rule the timeline uses, so a journey never counts as shared in
    // one view and separate in the other.
    function identityOf(leg) {
        return window.TripTeamTimeline.identityOf({
            item_type: 'leg',
            source_id: leg.leg_key,
            title: `${leg.from_label || ''} → ${leg.to_label || ''}`,
            selected_mode: leg.selected_mode,
        });
    }

    /**
     * One entry per journey, with everybody on it.
     *
     * Only legs the calculation produced are here. A member whose position the
     * plan cannot work out has no leg, so nothing is drawn for them - not even a
     * guess shown as a dashed line, which would still read as "roughly this way".
     */
    function journeys(plan, view = 'all') {
        const merged = new Map();
        (plan?.legs || []).forEach(leg => {
            if (view !== 'all' && leg.member_id !== view) return;
            const points = pointsOf(plan, leg);
            if (points.length < 2) return;
            const key = identityOf(leg);
            const entry = merged.get(key) || {
                key, points, members: [],
                mode: leg.selected_mode,
                label: `${leg.from_label || ''} → ${leg.to_label || ''}`,
                legKey: leg.leg_key,
            };
            if (leg.member_id) entry.members.push(memberName(plan, leg.member_id));
            merged.set(key, entry);
        });
        return [...merged.values()];
    }

    function incompleteMembers(plan, view = 'all') {
        const totals = plan?.itinerary_summary?.member_totals || {};
        return Object.entries(totals)
            .filter(([userId, total]) => total?.route_complete === false
                && (view === 'all' || userId === view))
            .map(([userId]) => memberName(plan, userId));
    }

    window.TripTeamJourneys = Object.freeze({
        journeys, endpoint, pointsOf, identityOf, incompleteMembers, memberName,
    });
})();
