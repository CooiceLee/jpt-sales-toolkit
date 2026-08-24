/** Tracks unsaved legacy visit-execution cards independently from briefings. */
(function() {
    const dirtyStops = new Set();

    function mark(stopId) { if (stopId) dirtyStops.add(String(stopId)); }
    function markClean(stopId) { dirtyStops.delete(String(stopId)); }
    function reset() { dirtyStops.clear(); }
    function isDirty(stopId = null) {
        return stopId == null ? dirtyStops.size > 0 : dirtyStops.has(String(stopId));
    }
    function guard(options = {}) {
        if (!dirtyStops.size) return false;
        const message = I18n.t('Save or discard visit execution changes before continuing.');
        if (options.silent) notify(message); else alert(message);
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
