/** Persist the schedule fields edited on an individual itinerary stop. */
window.saveTripStopSchedule = async function(stopId) {
    if (State.tripBusy || !State.currentTripPlan?.id) return;
    const stop = (State.currentTripPlan.stops || []).find(item => item.id === stopId);
    if (!stop) return;
    try {
        setTripBusy(true);
        const token = TripPlanIdentity.intend();
        const updated = await ApiClient.updateTripStop(State.currentTripPlan.id, stopId, {
            row_version: stop.row_version || null,
            ...TripStopScheduleControls.readPayload(stopId),
        });
        if (!TripPlanIdentity.accept(token, updated)) return;
        notify(I18n.t('Schedule details saved'));
        renderCurrentTripPlan();
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
    } catch (error) {
        console.error('Save stop schedule error:', error);
        await handleTripError(error, 'Save schedule details');
    } finally {
        setTripBusy(false);
    }
};
