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

    /**
     * Save the planning mode as soon as it changes.
     *
     * It decides which calculation runs and which panels belong on screen, so
     * leaving it in the route draft meant the plan on the server stayed in the
     * old mode: switching back to one traveller left the team panels up and the
     * next save still refused for having no team members.
     */
    async function planningModeChanged() {
        if (State.tripBusy) return;
        const plan = State.currentTripPlan;
        const select = document.getElementById('trip-planning-mode');
        const mode = select?.value;
        if (!plan?.id || !mode || mode === plan.planning_mode) return;
        // Switching mode changes which calculation runs, so the route has to be
        // worked out again from the server's copy. Anything in the draft goes
        // with it, and that is the reader's call to make, not a side effect.
        if (TripPlanningDraft.get()?.dirty && !confirm(t(
            'Changing how this plan is planned discards the unsaved route '
            + 'changes. Save the route first, or continue and lose them?'
        ))) {
            if (select) select.value = plan.planning_mode || 'legacy';
            return;
        }
        try {
            setTripBusy(true);
            const token = TripPlanIdentity.intend();
            const switched = await ApiClient.updateTripPlan(plan.id, {
                planning_mode: mode,
                row_version: plan.row_version || null,
            });
            if (!TripPlanIdentity.accept(token, switched)) return;
            notify(t(mode === 'team'
                ? 'Team planning is on. Add the people travelling.'
                : 'Single-traveller planning is on.'));
        } catch (err) {
            console.error('Change planning mode error:', err);
            if (select) select.value = plan.planning_mode || 'legacy';
            await handleTripError(err, 'Change planning mode');
            return;
        } finally {
            setTripBusy(false);
        }
        populateTripPlanForm(State.currentTripPlan, { committed: true });
        renderCurrentTripPlan();
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
        TripPlanRefresh.redrawVisits();
        renderTripMap();
    }

    window.TripPlanningModeActions = Object.freeze({ planningModeChanged });
})();
