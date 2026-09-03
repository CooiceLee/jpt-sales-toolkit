window.moveTripStop = async function(stopId, direction) {
    if (State.tripBusy) return;
    if (window.TripBriefingDraft?.guard?.()) return;
    if (window.TripVisitDraft?.guard?.()) return;
    const plan = State.currentTripPlan;
    if (!plan?.id) return;
    const stops = plan.stops || [];
    const index = stops.findIndex(stop => stop.id === stopId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= stops.length) return;

    let visibleDurations;
    try {
        visibleDurations = typeof window.readTripStopDurationPayload === 'function'
            ? window.readTripStopDurationPayload({ syncDraft: false })
            : Object.fromEntries(stops.map(stop => [
                stop.id, {
                    half_days: TripPlanningDraft.durationFor(stop.id, TripDuration.readStopDuration(stop)),
                    preferred_period: stop.preferred_period || 'auto', locked: Boolean(stop.schedule_locked),
                }
            ]));
    } catch (error) {
        alert(error.message);
        return;
    }
    const reordered = stops.slice();
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];

    reordered.forEach((stop, position) => { stop.sequence_no = position + 1; });
    TripPlanIdentity.accept(TripPlanIdentity.intend(),
        { ...plan, route_order_mode: 'manual', stops: reordered });
    TripPlanningDraft.change(draft => {
        draft.routeOrderMode = 'manual';
        draft.stopOrder = reordered.map(stop => stop.id);
        draft.stopDurations = { ...draft.stopDurations, ...visibleDurations };
    });
    setInputValue('trip-route-order-mode', 'manual');
    renderCurrentTripPlan();
    window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
    window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
    renderTripMap();
    notify(I18n.t('Stop order changed in the draft. Updating the preview; the route is not saved yet.'));
    TripTransportActions.schedulePreview();
};

window.saveTripStopResult = async function(stopId) {
    if (State.tripBusy) return;
    if (window.TripVisitDraft?.guard?.()) return;
    if (!State.currentTripPlan?.id) return;
    try {
        setTripBusy(true);
        const token = TripPlanIdentity.intend();
        const moved = await ApiClient.updateTripStop(State.currentTripPlan.id, stopId, {
            row_version: (State.currentTripPlan.stops || []).find(stop => stop.id === stopId)?.row_version || null,
            ...TripStopScheduleControls.readPayload(stopId),
            visit_purpose: document.getElementById(`stop-purpose-${stopId}`)?.value?.trim() || null,
            result_status: document.getElementById(`stop-result-${stopId}`)?.value || 'Planned',
            result_notes: document.getElementById(`stop-notes-${stopId}`)?.value?.trim() || null
        });
        if (!TripPlanIdentity.accept(token, moved)) return;
        notify(I18n.t('Visit details saved'));
        window.refreshTripStopCard?.(State.currentTripPlan, stopId);
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
    } catch (err) {
        console.error('Save stop error:', err);
        await handleTripError(err, 'Save stop');
    } finally {
        setTripBusy(false);
    }
};

async function runTripItinerary(action, options = {}) {
    if (State.tripBusy) return;
    if (window.TripBriefingDraft?.guard?.({ silent: Boolean(options.automatic) })) return;
    if (window.TripVisitDraft?.guard?.({ silent: Boolean(options.automatic) })) return;
    if (window.TripFreeStopDraft?.guardRouteAction?.(Boolean(options.automatic))) return;
    if (action === 'preview' && !State.currentTripPlan?.id) {
        alert(I18n.t('Create or select a trip plan before previewing the route.'));
        return;
    }
    window.TripTransportActions?.cancelScheduledPreview?.();
    setTripBusy(true);
    try {
        if (!State.currentTripPlan?.id) {
            await createTripPlanFromForm();
        }
        if (!State.currentTripPlan?.id) return;
        const payload = readTripItineraryPayload();
        const validationKey = window.TripRouteForm?.validationError?.(payload);
        if (validationKey) {
            const message = I18n.t(validationKey);
            if (options.automatic) notify(message);
            else alert(message);
            return;
        }
        const draftRevision = window.TripPlanningDraft?.revision?.() || 0;
        if (action !== 'preview') {
            payload.row_version = State.currentTripPlan.row_version || null;
        }
        const token = TripPlanIdentity.intend();
        const result = await ApiClient[action === 'preview' ? 'previewTripItinerary' : 'generateTripItinerary'](
            State.currentTripPlan.id,
            payload
        );
        const isCurrentRevision = window.TripPlanningDraft?.isCurrentRevision;
        if (action === 'preview' && isCurrentRevision && !isCurrentRevision(draftRevision)) {
            notify(I18n.t('The draft changed while previewing. Run the preview again.'));
            return;
        }
        if (!TripPlanIdentity.accept(token, result)) return;
        if (action === 'preview') window.TripPlanningDraft?.previewApplied?.(result, draftRevision);
        populateTripPlanForm(State.currentTripPlan, { committed: action !== 'preview' });
        if (action !== 'preview' && window.TripFreeStopForm?.isOpen?.()) {
            window.TripFreeStopForm.close({ force: true });
        }
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
        // A preview writes nothing, so the list of saved plans must not take its
        // dates: the row would show a date the plan does not have until a
        // refresh quietly puts the real one back.
        if (action !== 'preview') syncTripPlanListEntry(State.currentTripPlan);
        renderTripPlans();
        renderTripMap();
        notify(I18n.t(action === 'preview'
            ? (options.automatic ? 'Preview updated. Draft changes are not saved.' : 'Route preview ready. Draft changes are not saved.')
            : 'Route saved'));
    } catch (err) {
        console.error(`${action} itinerary error:`, err);
        await handleTripError(err, action === 'preview' ? 'Preview route' : 'Save route');
    } finally {
        setTripBusy(false);
    }
}

window.previewCurrentTripItinerary = async function(options = {}) { await runTripItinerary('preview', options); };
window.generateCurrentTripItinerary = async function() {
    await runTripItinerary('generate');
};
