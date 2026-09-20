/** The order of the stops that is actually in force.
 *
 * A manual move lives in the route draft until the route is saved, and the
 * preview that the move itself asks for comes back with the stops in the order
 * they are stored in. Reading the stored order back into the list made the move
 * look like it had done nothing - and a second move would then have been
 * measured against a list the reader was not seeing.
 *
 * One answer, used by the list, by the next move and by the note that says it
 * is not written yet. TripPlanningDraft.reconcile keeps the draft's order in
 * step with stops added and removed, so nothing deleted comes back through it.
 */
(function () {
    'use strict';

    const draft = () => window.TripPlanningDraft?.get?.() || null;

    function stops(list = []) {
        const current = draft();
        if (current?.routeOrderMode !== 'manual') return [...list];
        const byId = new Map(list.map(stop => [String(stop.id), stop]));
        const wanted = (current.stopOrder || []).map(id => byId.get(String(id))).filter(Boolean);
        return wanted.length === list.length ? wanted : [...list];
    }

    /** Whether what is on screen is ahead of what is stored. */
    function pending(list = []) {
        return stops(list).map(stop => String(stop.id)).join(',')
            !== list.map(stop => String(stop.id)).join(',');
    }

    window.TripStopOrder = Object.freeze({ stops, pending });
})();
