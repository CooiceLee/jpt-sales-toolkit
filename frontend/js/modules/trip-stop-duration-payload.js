/** Reading each stop's duration and AM/PM choice out of the visible form. */
function readTripStopDurationPayload(options = {}) {
    const durations = {};
    const routeDraft = window.TripPlanningDraft?.get?.();
    (State.currentTripPlan?.stops || []).forEach(stop => {
        const fallback = window.TripPlanningDraft?.durationFor?.(
            stop.id, TripDuration.readStopDuration(stop)
        ) ?? routeDraft?.stopDurations?.[stop.id]?.half_days
            ?? TripDuration.readStopDuration(stop);
        const visibleDays = document.getElementById(`stop-stay-${stop.id}`)?.value;
        const hasScheduleControls = Boolean(document.getElementById(`stop-period-${stop.id}`));
        const schedule = hasScheduleControls
            ? window.TripStopScheduleControls?.readPayload?.(stop.id)
            : (routeDraft?.stopDurations?.[stop.id] || stop);
        const parsedHalfDays = visibleDays === undefined
            ? TripDuration.normalizeHalfDays(fallback)
            : TripDuration.parseDisplayDays(visibleDays);
        if (parsedHalfDays == null) {
            throw new Error(I18n.t('Stop duration must be 0.5 to 30 days in 0.5-day increments.'));
        }
        durations[stop.id] = {
            half_days: parsedHalfDays,
            preferred_period: ['auto', 'AM', 'PM'].includes(schedule.preferred_period)
                ? schedule.preferred_period : 'auto',
            locked: Boolean(schedule.schedule_locked ?? schedule.locked),
        };
    });
    const changed = routeDraft && Object.entries(durations).some(
        ([stopId, duration]) => JSON.stringify(routeDraft.stopDurations?.[stopId] || {}) !== JSON.stringify(duration)
    );
    if (changed && options.syncDraft !== false) {
        window.TripPlanningDraft.change(draft => {
            draft.stopDurations = { ...draft.stopDurations, ...durations };
        });
    }
    return durations;
}
