/** Remove customer-linked route stops while preserving draft/save invariants. */
(function() {
    async function remove(stopId) {
        if (State.tripBusy || !State.currentTripPlan?.id) return;
        if (window.TripBriefingDraft?.guard?.()) return;
        if (window.TripVisitDraft?.guard?.()) return;
        if (window.TripFreeStopDraft?.guardRouteAction?.()) return;
        const stop = (State.currentTripPlan.stops || []).find(item => item.id === stopId);
        if (!stop) return;
        const isLastStop = (State.currentTripPlan.stops || []).length === 1;
        const message = isLastStop && window.TripPlanningDraft?.get?.()?.dirty
            ? I18n.t('Remove the final stop “{name}”? Unsaved route changes will also be discarded.', {
                name: stop.customer_name || I18n.t('Untitled')
            })
            : I18n.t('Remove this stop from the plan?');
        if (!confirm(message)) return;
        let shouldPreview = false;
        try {
            setTripBusy(true);
            State.currentTripPlan = await ApiClient.archiveTripStop(
                State.currentTripPlan.id, stopId, stop.row_version || null
            );
            if (window.TripFreeStopForm?.isOpen?.()) {
                window.TripFreeStopForm.close({ force: true });
            }
            if (!State.currentTripPlan?.stops?.length) {
                populateTripPlanForm(State.currentTripPlan, { committed: true });
            }
            notify(I18n.t('Stop removed'));
            State.tripCandidatePagination.offset = 0;
            await loadTripPlanner();
            shouldPreview = Boolean(State.currentTripPlan?.stops?.length);
            if (shouldPreview) TripPlanningDraft.change(() => {});
        } catch (error) {
            console.error('Remove stop error:', error);
            await handleTripError(error, 'Remove stop');
        } finally { setTripBusy(false); }
        if (shouldPreview) {
            notify(I18n.t('Stop removed. Updating the route preview; the route is not saved yet.'));
            await window.previewCurrentTripItinerary({ automatic: true });
        }
    }
    window.removeTripStop = remove;
})();
