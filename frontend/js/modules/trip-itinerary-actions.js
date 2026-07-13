window.moveTripStop = async function(stopId, direction) {
    if (State.tripBusy) return;
    const plan = State.currentTripPlan;
    if (!plan?.id) return;
    const stops = [...(plan.stops || [])];
    const index = stops.findIndex(stop => stop.id === stopId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= stops.length) return;

    const reordered = [...stops];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];

    try {
        setTripBusy(true);
        State.currentTripPlan = await ApiClient.reorderTripStops(
            plan.id,
            reordered.map(stop => stop.id),
            plan.row_version
        );
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
        renderTripMap();
        renderTripPlans();
    } catch (err) {
        console.error('Reorder trip stops error:', err);
        await handleTripError(err, 'Reorder stops');
    } finally {
        setTripBusy(false);
    }
};

window.saveTripStopResult = async function(stopId) {
    if (State.tripBusy) return;
    if (!State.currentTripPlan?.id) return;
    try {
        setTripBusy(true);
        State.currentTripPlan = await ApiClient.updateTripStop(State.currentTripPlan.id, stopId, {
            row_version: (State.currentTripPlan.stops || []).find(stop => stop.id === stopId)?.row_version || null,
            planned_date: document.getElementById(`stop-date-${stopId}`)?.value || null,
            stay_days: Number(document.getElementById(`stop-stay-${stopId}`)?.value || 1),
            visit_purpose: document.getElementById(`stop-purpose-${stopId}`)?.value?.trim() || null,
            result_status: document.getElementById(`stop-result-${stopId}`)?.value || 'Planned',
            result_notes: document.getElementById(`stop-notes-${stopId}`)?.value?.trim() || null
        });
        notify('Stop saved');
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
    } catch (err) {
        console.error('Save stop error:', err);
        await handleTripError(err, 'Save stop');
    } finally {
        setTripBusy(false);
    }
};

async function runTripItinerary(action) {
    if (State.tripBusy) return;
    setTripBusy(true);
    try {
        if (!State.currentTripPlan?.id) {
            await createTripPlanFromForm();
        }
        if (!State.currentTripPlan?.id) return;
        const payload = {
            ...readTripPlanFormPayload(),
            stop_stays: readTripStopStayPayload()
        };
        if (action !== 'preview') {
            payload.row_version = State.currentTripPlan.row_version || null;
        }
        State.currentTripPlan = await ApiClient[action === 'preview' ? 'previewTripItinerary' : 'generateTripItinerary'](
            State.currentTripPlan.id,
            payload
        );
        populateTripPlanForm(State.currentTripPlan);
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
        renderTripPlans();
        renderTripMap();
        notify(action === 'preview' ? 'Route preview ready' : 'Route saved');
    } catch (err) {
        console.error(`${action} itinerary error:`, err);
        await handleTripError(err, action === 'preview' ? 'Preview route' : 'Save route');
    } finally {
        setTripBusy(false);
    }
}

window.previewCurrentTripItinerary = async function() {
    await runTripItinerary('preview');
};

window.generateCurrentTripItinerary = async function() {
    await runTripItinerary('generate');
};

window.removeTripStop = async function(stopId) {
    if (State.tripBusy) return;
    if (!State.currentTripPlan?.id) return;
    if (!confirm('Remove this stop from the plan?')) return;
    try {
        setTripBusy(true);
        const stop = (State.currentTripPlan.stops || []).find(item => item.id === stopId);
        State.currentTripPlan = await ApiClient.archiveTripStop(
            State.currentTripPlan.id,
            stopId,
            stop?.row_version || null
        );
        notify('Stop removed');
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner();
    } catch (err) {
        console.error('Remove stop error:', err);
        await handleTripError(err, 'Remove stop');
    } finally {
        setTripBusy(false);
    }
};

window.exportCurrentTripPlan = async function(format) {
    if (!State.currentTripPlan?.id) {
        alert('Select a trip plan first');
        return;
    }
    try {
        const { blob, filename } = await ApiClient.exportTripPlan(State.currentTripPlan.id, format);
        downloadBlob(blob, filename);
    } catch (err) {
        console.error('Export trip plan error:', err);
        alert('Error exporting trip plan: ' + (err.message || 'Unknown error'));
    }
};

