/** Edit one transport leg in the current route draft. */
(function() {
    function numberOrNull(value) {
        if (value === '' || value == null) return null;
        const number = Number(value);
        return Number.isFinite(number) && number >= 0 ? number : null;
    }

    function change(index, schedulePreview) {
        if (State.tripBusy) return;
        const leg = State.currentTripPlan?.legs?.[index];
        if (!leg?.leg_key) return;
        const selectedInput = document.getElementById(`trip-leg-mode-${index}`);
        const locked = Boolean(document.getElementById(`trip-leg-lock-${index}`)?.checked);
        const selected = selectedInput?.value || (locked ? leg.selected_mode : null);
        const manualDistance = numberOrNull(document.getElementById(`trip-leg-distance-${index}`)?.value);
        const manualHours = numberOrNull(document.getElementById(`trip-leg-hours-${index}`)?.value);
        const manualDaysRaw = document.getElementById(`trip-leg-days-${index}`)?.value;
        const manualHalfDays = manualDaysRaw === '' || manualDaysRaw == null
            ? null : TripDuration.parseDisplayTravelDays(manualDaysRaw);
        const durationInput = document.getElementById(`trip-leg-days-${index}`);
        const durationError = manualDaysRaw !== '' && manualDaysRaw != null && manualHalfDays == null
            ? I18n.t('Travel duration must be 0 to 30 days in 0.5-day increments.') : '';
        durationInput?.setCustomValidity?.(durationError);
        if (durationError) { notify(durationError); return; }
        TripPlanningDraft.change(draft => {
            if (!selected && !locked) {
                delete draft.legOverrides[leg.leg_key];
                return;
            }
            draft.legOverrides[leg.leg_key] = {
                selected_mode: selected,
                mode_locked: locked,
                manual_distance_km: manualDistance,
                manual_time_hours: manualHours,
                manual_travel_half_days: manualHalfDays,
                notes: document.getElementById(`trip-leg-notes-${index}`)?.value?.trim() || null,
            };
        });
        if (selected === 'other' && !(manualHours > 0 || manualHalfDays > 0)) {
            notify(I18n.t('Other transport requires manual travel hours or travel days before previewing.'));
            return;
        }
        schedulePreview();
    }

    window.TripLegActions = Object.freeze({ change });
})();
