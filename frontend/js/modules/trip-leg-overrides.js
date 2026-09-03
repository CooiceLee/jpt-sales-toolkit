/** What the saved legs say the traveller has already decided.

The server hands back every calculated leg. Only some of them carry a decision:
a transport mode somebody chose, hours or days they typed, an airport they
searched for. Those become the route draft's starting point; the rest are
output, and treating output as a decision would make each run an anchor for the
next one.
*/
(function() {
    function decided(leg, source) {
        // A saved airport counts on its own - the server keeps airports through
        // a plain regeneration, and locking the leg is a separate decision.
        // Not selected_mode: every calculated leg has one, so counting it
        // would turn each run's own output into an anchor for the next.
        return leg.has_override || leg.override_applied || source.mode_locked
            || source.manual_distance_km != null
            || source.manual_time_hours != null
            || source.manual_travel_half_days != null
            || source.manual_travel_days != null
            || source.departure_airport_name || source.arrival_airport_name
            || source.notes;
    }

    function fromPlan(plan, modes = []) {
        const clean = value => TripRouteValues.cleanLegOverride(
            value, modes, window.TripLegAirports?.FIELDS || []);
        const result = {};
        (plan?.legs || []).forEach(leg => {
            const source = { ...(leg.override || leg) };
            if (source.selected_mode === 'other') {
                source.manual_distance_km ??= leg.distance_km;
                source.manual_time_hours ??= leg.time_hours;
                source.manual_travel_half_days ??= leg.travel_half_days != null
                    ? leg.travel_half_days
                    : (leg.travel_days != null
                        ? TripDuration.fromDisplayTravelDays(leg.travel_days) : null);
            }
            if (leg.leg_key && decided(leg, source)) {
                result[leg.leg_key] = clean(source);
            }
        });
        return result;
    }

    window.TripLegOverrides = Object.freeze({ fromPlan });
})();
