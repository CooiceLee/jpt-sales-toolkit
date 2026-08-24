/** CRUD and explicit geocoding actions for non-customer itinerary stops. */
(function() {
    let geocodeEpoch = 0;
    function acceptPlan(plan, duration = null) {
        State.currentTripPlan = plan;
        State.tripPlans = (State.tripPlans || []).map(item => item.id === plan.id
            ? { ...item, stop_count: (plan.stops || []).length, row_version: plan.row_version }
            : item);
        const hasStops = Boolean(plan.stops?.length);
        populateTripPlanForm(plan, { committed: !hasStops });
        if (hasStops) TripPlanningDraft.change(draft => {
            if (duration?.id) draft.stopDurations[duration.id] = {
                ...(draft.stopDurations[duration.id] || {}), half_days: duration.halfDays,
            };
        });
        renderTripPlans();
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(plan);
        window.TripScheduleView?.renderPlan?.(plan);
        renderTripMap();
    }
    async function save() {
        if (State.tripBusy || !State.currentTripPlan?.id) return;
        if (window.TripBriefingDraft?.guard?.()) return;
        if (window.TripVisitDraft?.guard?.()) return;
        let payload;
        try { payload = TripFreeStopForm.payload(); }
        catch (error) { alert(error.message); return; }
        const stopId = TripFreeStopForm.editingId();
        if (stopId) payload.row_version = TripFreeStopForm.rowVersion();
        else payload.sequence_no = (State.currentTripPlan.stops || []).length + 1;
        let committed = false;
        try {
            setTripBusy(true);
            TripFreeStopForm.setBusy(true);
            const plan = await ApiClient[stopId ? 'updateTripFreeStop' : 'addTripFreeStop'](
                State.currentTripPlan.id, ...(stopId ? [stopId, payload] : [payload])
            );
            const saved = (plan.stops || []).find(item => item.id === stopId)
                || [...(plan.stops || [])].reverse().find(item => item.stop_kind === 'free');
            acceptPlan(plan, saved ? { id: saved.id, halfDays: payload.duration_half_days } : null);
            TripFreeStopForm.close({ force: true });
            committed = true;
            notify(I18n.t(stopId ? 'Personal stop updated. Preview and save the route.'
                : 'Personal stop added. Preview and save the route.'));
        } catch (error) {
            console.error('Save personal stop error:', error);
            if (error?.name === 'ConflictError') {
                await loadTripPlanner();
                TripFreeStopForm.close({ force: true });
                alert(I18n.t('This personal stop changed elsewhere. Latest data was loaded; reopen the editor and try again.'));
            } else await handleTripError(error, 'Save personal stop');
        } finally {
            TripFreeStopForm.setBusy(false);
            setTripBusy(false);
        }
        if (committed && State.currentTripPlan?.stops?.length) TripTransportActions.schedulePreview();
    }
    async function archive(stopId) {
        if (State.tripBusy || !State.currentTripPlan?.id) return;
        if (window.TripBriefingDraft?.guard?.()) return;
        if (window.TripVisitDraft?.guard?.()) return;
        const stop = (State.currentTripPlan.stops || []).find(item => item.id === stopId && item.stop_kind === 'free');
        if (!stop) return;
        if (TripFreeStopDraft.isDirty() && !TripFreeStopDraft.confirmDiscard(
            'Discard unsaved personal stop changes and remove a stop?'
        )) return;
        const isLastStop = (State.currentTripPlan.stops || []).length === 1;
        const message = isLastStop && TripPlanningDraft.get()?.dirty
            ? I18n.t('Remove the final stop “{name}”? Unsaved route changes will also be discarded.', {
                name: stop.location_name || stop.customer_name || I18n.t('Untitled')
            })
            : I18n.t('Remove personal stop “{name}” from this plan?', {
                name: stop.location_name || stop.customer_name || I18n.t('Untitled')
            });
        if (!confirm(message)) return;
        let committed = false;
        try {
            setTripBusy(true);
            const plan = await ApiClient.archiveTripFreeStop(State.currentTripPlan.id, stopId, stop.row_version || null);
            acceptPlan(plan);
            TripFreeStopForm.close({ force: true });
            committed = true;
            notify(I18n.t('Personal stop removed. Preview and save the route.'));
        } catch (error) {
            console.error('Remove personal stop error:', error);
            if (error?.name === 'ConflictError') {
                await loadTripPlanner();
                TripFreeStopForm.close({ force: true });
                alert(I18n.t('This personal stop changed elsewhere. Latest data was loaded; reopen the editor and try again.'));
            } else await handleTripError(error, 'Remove personal stop');
        } finally { setTripBusy(false); }
        if (committed && State.currentTripPlan?.stops?.length) TripTransportActions.schedulePreview();
    }
    async function searchPosition() {
        const fields = TripFreeStopForm.geocodeFields();
        if (!Object.values(fields).some(Boolean)) {
            alert(I18n.t('Enter an address, city, postal code, or country first.'));
            return;
        }
        if (typeof navigator !== 'undefined' && navigator.onLine === false) {
            TripFreeStopForm.status('Location search is unavailable offline. Enter coordinates manually or retry online.', 'error');
            return;
        }
        const epoch = ++geocodeEpoch;
        const contextVersion = TripFreeStopForm.contextVersion();
        const fingerprint = JSON.stringify(fields);
        const isCurrent = () => epoch === geocodeEpoch
            && contextVersion === TripFreeStopForm.contextVersion()
            && fingerprint === JSON.stringify(TripFreeStopForm.geocodeFields());
        TripFreeStopForm.setBusy(true);
        TripFreeStopForm.status('Searching location...', 'loading');
        TripFreeStopForm.renderCandidates([]);
        try {
            const result = await ApiClient.searchGeocode(fields, 5);
            if (!isCurrent()) return;
            const candidates = result.candidates || [];
            TripFreeStopForm.renderCandidates(candidates, result.provider || '');
            if (!candidates.length) TripFreeStopForm.status(
                'No matching location found. Refine the address or enter exact coordinates manually.', 'error'
            );
        } catch (error) {
            if (!isCurrent()) return;
            console.error('Personal stop geocode error:', error);
            TripFreeStopForm.status('Location search failed. Check the network or enter coordinates manually.', 'error');
        } finally {
            if (isCurrent()) TripFreeStopForm.setBusy(false);
        }
    }
    function cancelGeocode() {
        geocodeEpoch += 1;
        TripFreeStopForm.setBusy(false);
    }
    window.TripFreeStopActions = Object.freeze({ save, archive, searchPosition, cancelGeocode });
})();
