/** Tracks unsaved legacy visit-execution cards independently from briefings. */
(function() {
    const dirtyStops = new Set();

    function mark(stopId) { if (stopId) dirtyStops.add(String(stopId)); }
    function markClean(stopId) { dirtyStops.delete(String(stopId)); }
    function reset() { dirtyStops.clear(); }
    function isDirty(stopId = null) {
        return stopId == null ? dirtyStops.size > 0 : dirtyStops.has(String(stopId));
    }
    function dirtyNames() {
        const stops = State.currentTripPlan?.stops || [];
        const names = [...dirtyStops].map(id => {
            const stop = stops.find(item => String(item.id) === id);
            return stop?.customer_name || stop?.location_name || null;
        }).filter(Boolean);
        return names.length ? names.join(', ') : I18n.t('a visit card');
    }
    function guard(options = {}) {
        if (!dirtyStops.size) return false;
        if (options.silent) {
            notify(I18n.t('Save or discard visit execution changes before continuing.'));
            return true;
        }
        // Offer the same escape the route, personal-stop and briefing drafts give,
        // otherwise an edited visit card blocks every action until the app restarts.
        if (confirm(I18n.t('Unsaved visit execution changes for {names} will be discarded. Continue?',
            { names: dirtyNames() }))) {
            reset();
            return false;
        }
        return true;
    }
    function discard(stopId) {
        markClean(stopId);
        window.TripPlannerModule?.refreshVisitCard?.(State.currentTripPlan, stopId);
    }
    window.TripVisitDraft = Object.freeze({ mark, markClean, reset, isDirty, guard, discard });
    window.addEventListener?.('beforeunload', event => {
        if (!dirtyStops.size) return;
        event.preventDefault(); event.returnValue = '';
    });
})();
