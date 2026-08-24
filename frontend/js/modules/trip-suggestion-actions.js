/** User-triggered transport search and explicit apply-to-draft actions. */
(function() {
    function decode(token) {
        try { return decodeURIComponent(token); } catch { return ''; }
    }
    function numberOrNull(value) {
        if (value === '' || value == null) return null;
        const number = Number(value);
        return Number.isFinite(number) && number >= 0 ? number : null;
    }
    async function searchRoute(forceRefresh = false, focusLegKey = null) {
        if (window.TripFreeStopDraft?.guardRouteAction?.()) return;
        const plan = State.currentTripPlan;
        if (!plan?.id || !plan.legs?.length) {
            alert(I18n.t('Preview the route before searching travel options.'));
            return;
        }
        let payload;
        try { payload = readTripItineraryPayload(); }
        catch (error) { alert(error.message); return; }
        const validationKey = window.TripRouteForm?.validationError?.(payload);
        if (validationKey) { alert(I18n.t(validationKey)); return; }
        const revision = TripPlanningDraft.revision();
        const requestEpoch = TripSuggestionState.begin(plan.id, revision, focusLegKey);
        TripSuggestionView.render(plan);
        if (typeof navigator !== 'undefined' && navigator.onLine === false) {
            notify(I18n.t('Offline mode: local estimates may still work, but live source links require a connection.'));
        }
        try {
            const response = await ApiClient.getTripTransportSuggestions(plan.id, {
                ...payload, row_version: plan.row_version || null, force_refresh: Boolean(forceRefresh),
            });
            TripSuggestionState.succeed(requestEpoch, response);
        } catch (error) {
            console.error('Transport suggestion error:', error);
            TripSuggestionState.fail(requestEpoch,
                error?.message === 'Failed to fetch'
                    ? 'Travel option search is unavailable. Check the network and retry.'
                    : error?.message || 'Travel option search failed.');
        }
        TripSuggestionView.render(State.currentTripPlan);
    }
    function searchLeg(index) {
        const leg = State.currentTripPlan?.legs?.[index];
        if (leg?.leg_key) searchRoute(false, leg.leg_key);
    }
    function apply(token) {
        if (window.TripFreeStopDraft?.guardRouteAction?.()) return;
        const suggestionId = decode(token);
        const item = TripSuggestionState.get().suggestions.find(candidate => candidate.suggestion_id === suggestionId);
        if (!item || TripSuggestionState.stale()) {
            notify(I18n.t('This suggestion is stale. Search again before applying it.'));
            return;
        }
        if (!(State.currentTripPlan?.legs || []).some(leg => leg.leg_key === item.leg_key)) return;
        const hours = numberOrNull(item.time_hours);
        const halfDays = item.travel_half_days != null
            ? TripDuration.normalizeTravelHalfDays(item.travel_half_days)
            : (item.travel_days != null ? TripDuration.fromDisplayTravelDays(item.travel_days) : null);
        if (item.mode === 'other' && !(hours > 0 || halfDays > 0)) {
            alert(I18n.t('Other transport requires manual travel hours or travel days before previewing.'));
            return;
        }
        TripPlanningDraft.change(draft => {
            const current = draft.legOverrides[item.leg_key] || {};
            draft.legOverrides[item.leg_key] = {
                selected_mode: item.mode, mode_locked: true,
                manual_distance_km: numberOrNull(item.distance_km), manual_time_hours: hours,
                manual_travel_half_days: halfDays,
                notes: item.notes || item.attribution || current.notes || null,
            };
        });
        TripSuggestionState.markApplied();
        TripTransportView.render(State.currentTripPlan, TripPlanningDraft.get());
        notify(I18n.t('Suggestion added to the current route. Preview it, then save the route.'));
    }
    function ignore(token) {
        TripSuggestionState.ignore(decode(token));
        TripSuggestionView.render(State.currentTripPlan);
    }
    window.TripSuggestionActions = Object.freeze({ searchRoute, searchLeg, apply, ignore });
})();
