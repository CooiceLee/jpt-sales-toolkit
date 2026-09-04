/** Saving the time a customer agreed to, which the route is planned around. */
(function() {
    const t = (key, params = {}) => I18n.t(key, params);

    /**
     * An agreed time is saved as soon as it is entered.
     *
     * It is not a draft preference: the calculation reads a locked visit's time
     * from the stop itself, so leaving it in the draft would mean the preview
     * ignored what was just typed. Saving first, then previewing, is what makes
     * "plan around the times I agreed" actually happen.
     */
    async function appointmentChanged(stopId) {
        if (State.tripBusy) return;
        const plan = State.currentTripPlan;
        const stop = (plan?.stops || []).find(item => item.id === stopId);
        if (!plan?.id || !stop) return;
        const payload = window.TripStopScheduleControls.readPayload(stopId);
        const wanted = document.getElementById(`stop-schedule-lock-${stopId}`);
        if (wanted?.checked && !payload.planned_date) {
            notify(t('Enter the agreed date, then confirm it here.'));
            wanted.checked = false;
            return;
        }
        try {
            setTripBusy(true);
            const token = TripPlanIdentity.intend();
            const saved = await ApiClient.updateTripStop(
                plan.id, stopId,
                { row_version: stop.row_version || null, ...payload },
            );
            if (!TripPlanIdentity.accept(token, saved)) return;
            notify(t(payload.schedule_locked
                ? 'Agreed time saved. The route will be planned around it.'
                : 'Visit time saved.'));
            window.refreshTripStopCard?.(State.currentTripPlan, stopId);
            TripPlanRefresh.redrawVisits();
            window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
            renderTripMap();
        } catch (err) {
            console.error('Save agreed visit time error:', err);
            await handleTripError(err, 'Save agreed visit time');
            renderCurrentTripPlan();
            return;
        } finally {
            setTripBusy(false);
        }
        window.TripTransportActions?.schedulePreview?.();
    }

    window.TripStopScheduleActions = Object.freeze({ appointmentChanged });
})();

/** Switching how a plan is planned. */
(function() {
    const t = (key, params = {}) => I18n.t(key, params);

})();
