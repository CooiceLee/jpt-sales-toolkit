/** Read one plan back from the server and redraw what it feeds.

Reloading the whole planner stops when another editor is holding unsaved work,
and says nothing when it does - so a save could report success over a screen
still showing the previous calculation. Re-reading the plan on its own always
happens, and leaves other editors' unsaved work where it is.
*/
(function() {
    /** Redraw the visit execution cards, unless one is being written in.

    The cards are typed into directly and a redraw rebuilds them from the
    server, so anything half-written in one is gone. Where the redraw is a side
    effect of something else - a plan re-read, an agreed time saved, a mode
    switch - it waits. Choosing another day is not a side effect: there the
    cards have to change, and the reader is asked before their work goes.
    */
    function redrawVisits() {
        if (window.TripVisitDraft?.isDirty?.()) return false;
        window.TripPlannerModule?.renderVisitExecution?.(State.currentTripPlan);
        return true;
    }

    async function reread(planId, { token } = {}) {
        if (!planId) return false;
        // A caller that is finishing something it started earlier hands in the
        // number it took then. Reading the current number here instead would
        // borrow whatever the reader has since asked for, and this re-read
        // would then be allowed to answer in their place.
        const epoch = token ?? TripPlanIdentity.intend();
        if (!TripPlanIdentity.isCurrent(epoch)) return false;
        const plan = await ApiClient.getTripPlan(planId);
        // The reader may have opened another plan while this was in flight.
        if (!TripPlanIdentity.accept(epoch, plan)) return false;
        populateTripPlanForm(State.currentTripPlan);
        syncTripPlanListEntry(State.currentTripPlan);
        renderTripPlans();
        renderCurrentTripPlan();
        redrawVisits();
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
        renderTripMap();
        return true;
    }

    window.TripPlanRefresh = Object.freeze({ reread, redrawVisits });
})();
