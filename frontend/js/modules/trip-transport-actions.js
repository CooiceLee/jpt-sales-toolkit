/** Mutate the local Trip route draft and trigger read-only impact previews. */
(function() {
    let previewTimer = null;
    function schedulePreview() {
        clearTimeout(previewTimer);
        const plan = State.currentTripPlan;
        if (!plan?.id || !plan.stops?.length) return;
        previewTimer = setTimeout(() => {
            previewTimer = null;
            if (!State.tripBusy) window.previewCurrentTripItinerary({ automatic: true });
        }, 350);
    }
    function cancelScheduledPreview() {
        clearTimeout(previewTimer);
        previewTimer = null;
    }
    function toggleMode(mode, enabled) {
        if (State.tripBusy) return;
        const current = TripPlanningDraft.get();
        if (!current) return;
        if (!enabled && current.transportModePriority.length === 1) {
            alert(I18n.t('Select at least one transport mode.'));
            TripTransportView.render(State.currentTripPlan, current);
            return;
        }
        TripPlanningDraft.change(draft => {
            draft.transportModePriority = enabled
                ? [...draft.transportModePriority, mode]
                : draft.transportModePriority.filter(item => item !== mode);
        });
        schedulePreview();
    }
    function moveMode(mode, direction) {
        if (State.tripBusy) return;
        const current = TripPlanningDraft.get();
        const index = current?.transportModePriority?.indexOf(mode) ?? -1;
        const target = index + Number(direction);
        if (index < 0 || target < 0 || target >= current.transportModePriority.length) return;
        TripPlanningDraft.change(draft => {
            [draft.transportModePriority[index], draft.transportModePriority[target]] =
                [draft.transportModePriority[target], draft.transportModePriority[index]];
        });
        schedulePreview();
    }

    function routeModeChanged(value) {
        if (State.tripBusy) return;
        const nextMode = value === 'manual' ? 'manual' : 'auto';
        let clearedOverrides = false;
        TripPlanningDraft.change(draft => {
            if (draft.routeOrderMode === 'manual' && nextMode === 'auto'
                && Object.keys(draft.legOverrides || {}).length) {
                draft.legOverrides = {};
                clearedOverrides = true;
            }
            draft.routeOrderMode = nextMode;
            if (nextMode !== 'manual') Object.values(draft.stopDurations || {}).forEach(item => {
                item.locked = false;
            });
        });
        (State.currentTripPlan?.stops || []).forEach(stop => {
            const control = document.getElementById(`stop-schedule-lock-${stop.id}`);
            if (!control) return;
            control.disabled = nextMode !== 'manual' || !stop.planned_date;
            if (control.disabled) control.checked = false;
            control.parentElement?.setAttribute('title', I18n.t(control.disabled
                ? 'Plan a date and choose Manual order to lock this visit.'
                : 'Keep this visit at its current time when updating the route.'));
        });
        if (clearedOverrides) {
            notify(I18n.t('Manual leg settings were cleared because automatic order may change the route.'));
        }
        schedulePreview();
    }

    function headerChanged() {
        if (State.tripBusy) return;
        TripPlanningDraft.change(draft => {
            draft.departureWindowStart = document.getElementById('trip-departure-window-start')?.value || '';
            draft.departureWindowEnd = document.getElementById('trip-departure-window-end')?.value || '';
            draft.returnWindowStart = document.getElementById('trip-return-window-start')?.value || '';
            draft.returnWindowEnd = document.getElementById('trip-return-window-end')?.value || '';
        });
        schedulePreview();
    }

    function hubChanged(kind, code) {
        if (State.tripBusy || code === 'custom') return;
        if (!window.TripChinaHubs?.apply?.(kind, code)) return;
        routeFieldChanged();
    }

    function stayChanged(stopId, value) {
        if (State.tripBusy) return;
        const duration = TripDuration.parseDisplayDays(value);
        const input = document.getElementById(`stop-stay-${stopId}`);
        const error = duration == null
            ? I18n.t('Stop duration must be 0.5 to 30 days in 0.5-day increments.') : '';
        input?.setCustomValidity?.(error);
        if (error) return;
        TripPlanningDraft.change(draft => {
            draft.stopDurations[stopId] = { ...(draft.stopDurations[stopId] || {}), half_days: duration };
        });
        notify(I18n.t('Stay changed in the draft. Updating the preview; the route is not saved yet.'));
        schedulePreview();
    }

    function schedulePreferenceChanged(stopId) {
        if (State.tripBusy) return;
        const schedule = TripStopScheduleControls.readPayload(stopId);
        TripPlanningDraft.change(draft => {
            draft.stopDurations[stopId] = {
                ...(draft.stopDurations[stopId] || {}),
                preferred_period: schedule.preferred_period,
                locked: schedule.schedule_locked,
            };
        });
        schedulePreview();
    }

    function routeFieldChanged() {
        if (State.tripBusy || !TripPlanningDraft.get()) return;
        TripPlanningDraft.change(draft => {
            draft.header = readTripPlanHeaderFormPayload();
        });
        schedulePreview();
    }

    function legChanged(index) {
        // TripLegActions owns manual_time_hours/manual_travel_half_days payload construction.
        return TripLegActions.change(index, schedulePreview);
    }

    window.TripTransportActions = Object.freeze({
        toggleMode, moveMode, routeModeChanged, headerChanged, stayChanged, legChanged,
        hubChanged, routeFieldChanged, schedulePreferenceChanged, schedulePreview, cancelScheduledPreview,
    });
})();
