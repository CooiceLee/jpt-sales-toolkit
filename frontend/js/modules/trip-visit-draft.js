/** Tracks unsaved legacy visit-execution cards independently from briefings. */
(function() {
    const dirtyStops = new Set();

    // The bar says *which* card is holding the route up and goes to that one,
    // so what it depends on is the first unsaved card, not merely whether one
    // exists. With A and B both unsaved, discarding A leaves "still unsaved"
    // true either way, and the bar went on naming A while "go to it" - which
    // re-derives on the click - arrived at B.
    //
    // Typing again into the card already named changes nothing here, so this
    // still does not redraw on every keystroke.
    function changed(edit) {
        const before = [...dirtyStops][0] || null;
        edit();
        if (([...dirtyStops][0] || null) !== before) window.TripRouteBar?.render?.();
    }
    function mark(stopId) { if (stopId) changed(() => dirtyStops.add(String(stopId))); }
    function markClean(stopId) { changed(() => dirtyStops.delete(String(stopId))); }
    function reset() { changed(() => dirtyStops.clear()); }
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
    // Which card, not just "a card": execution renders one card per stop, so
    // the thing holding the route up has an id and a name, and both are needed
    // to say what it is and to bring the reader to it.
    function firstDirty() {
        const id = [...dirtyStops][0];
        if (!id) return null;
        const stop = (State.currentTripPlan?.stops || [])
            .find(item => String(item.id) === id);
        return { id, name: stop?.customer_name || stop?.location_name || '' };
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
    window.TripVisitDraft = Object.freeze({ mark, markClean, reset, isDirty, guard,
        discard, firstDirty, dirtyNames });
    window.addEventListener?.('beforeunload', event => {
        if (!dirtyStops.size) return;
        event.preventDefault(); event.returnValue = '';
    });
})();
