window.createTripPlanFromForm = async function() {
    if (window.TripBriefingDraft?.guard?.()) return;
    if (window.TripVisitDraft?.guard?.()) return;
    if (State.currentTripPlan?.id && window.TripPlanningDraft?.get?.()?.dirty
        && !confirm(I18n.t('Discard unsaved route changes and create a new plan?'))) return;
    if (window.TripFreeStopDraft?.isDirty?.()
        && !window.TripFreeStopDraft.confirmDiscard(
            'Discard unsaved personal stop changes and create a new plan?'
        )) return;
    const payload = { ...readTripPlanFormPayload(), status: 'Draft' };
    const token = TripPlanIdentity.intend();
    try {
        const created = await ApiClient.createTripPlan(payload);
        if (!TripPlanIdentity.accept(token, created)) return;
        populateTripPlanForm(State.currentTripPlan, { committed: true });
        notify(I18n.t('Trip plan created'));
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner({ token });
    } catch (err) {
        console.error('Create trip plan error:', err);
        alert(I18n.t('Error creating trip plan: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};

window.selectTripPlan = async function(planId) {
    if (State.currentTripPlan?.id !== planId && window.TripBriefingDraft?.guard?.()) return;
    if (State.currentTripPlan?.id !== planId && window.TripVisitDraft?.guard?.()) return;
    if (State.currentTripPlan?.id !== planId && window.TripPlanningDraft?.get?.()?.dirty
        && !confirm(I18n.t('Discard unsaved route changes and switch plans?'))) return;
    if (State.currentTripPlan?.id !== planId && window.TripFreeStopDraft?.isDirty?.()
        && !window.TripFreeStopDraft.confirmDiscard(
            'Discard unsaved personal stop changes and switch plans?'
        )) return;
    try {
        if (State.currentTripPlan?.id !== planId) window.TripVisitDraft?.reset?.();
        const token = TripPlanIdentity.intend();
        const plan = await ApiClient.getTripPlan(planId);
        if (!TripPlanIdentity.accept(token, plan)) return;
        populateTripPlanForm(State.currentTripPlan, { committed: true });
        renderTripPlans();
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
        renderTripMap();
    } catch (err) {
        console.error('Select trip plan error:', err);
    }
};

function renderTripPlans() {
    const container = document.getElementById('trip-plan-list');
    if (!container) return;
    const plans = State.tripPlans || [];
    if (!plans.length) {
        container.innerHTML = `<div class="empty-state compact">${escapeHtml(I18n.t('No saved plans'))}</div>`;
        return;
    }
    container.innerHTML = plans.map(plan => `
        <div class="trip-plan-row ${State.currentTripPlan?.id === plan.id ? 'active' : ''}">
            <button type="button" class="trip-plan-select" onclick="selectTripPlan('${plan.id}')">
                <span>
                    <strong>${escapeHtml(plan.title || I18n.t('Untitled'))}</strong>
                    <small>${escapeHtml(formatTripPlanDateRange(plan))}</small>
                </span>
                <em>${plan.stop_count || 0}</em>
            </button>
            <button type="button" class="trip-plan-archive"
                aria-label="${escapeHtml(I18n.t('Archive trip plan'))}"
                onclick="archiveTripPlan('${plan.id}', ${Number(plan.row_version) || 1})">&times;</button>
        </div>
    `).join('');
}

window.archiveTripPlan = async function(planId, rowVersion) {
    if (State.currentTripPlan?.id === planId && window.TripBriefingDraft?.guard?.()) return;
    if (State.currentTripPlan?.id === planId && window.TripVisitDraft?.guard?.()) return;
    const plan = (State.tripPlans || []).find(item => item.id === planId);
    if (State.currentTripPlan?.id === planId && window.TripPlanningDraft?.get?.()?.dirty
        && !confirm(I18n.t('This plan has unsaved route changes. Discard them and continue archiving?'))) return;
    if (State.currentTripPlan?.id === planId && window.TripFreeStopDraft?.isDirty?.()
        && !window.TripFreeStopDraft.confirmDiscard(
            'Discard unsaved personal stop changes and archive this plan?'
        )) return;
    if (!plan || !confirm(I18n.t('Archive trip plan “{title}”?', {
        title: plan.title || I18n.t('Untitled')
    }))) return;
    const token = TripPlanIdentity.intend();
    try {
        await ApiClient.archiveTripPlan(planId, rowVersion);
        // Both steps below check this action's number themselves.
        if (State.currentTripPlan?.id === planId) TripPlanIdentity.clear(token);
        notify(I18n.t('Trip plan archived'));
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner({ token });
    } catch (err) {
        console.error('Archive trip plan error:', err);
        await handleTripError(err, 'Archive trip plan');
    }
};

window.addCandidateToCurrentPlan = async function(index) {
    if (State.tripBusy) return;
    if (window.TripBriefingDraft?.guard?.()) return;
    if (window.TripVisitDraft?.guard?.()) return;
    const item = State.tripCandidates[index];
    if (!item) return;
    if (!TripCandidateState.hasExactCoordinates(item)) {
        alert(I18n.t('Precise coordinates are required. Open Coordinate Review and save the location first.'));
        return;
    }
    if (!State.currentTripPlan) {
        await createTripPlanFromForm();
    }
    if (!State.currentTripPlan?.id) return;

    let allowDuplicate = false;
    if (TripCandidateState.alreadyInPlan(item)) {
        allowDuplicate = confirm(I18n.t('{customer} is already in this plan. Create another visit instance?', {
            customer: item.customer_name || I18n.t('This customer')
        }));
        if (!allowDuplicate) return;
    }

    let shouldPreview = false;
    try {
        setTripBusy(true);
        const token = TripPlanIdentity.intend();
        const withStop = await ApiClient.addTripStop(State.currentTripPlan.id, {
            customer_id: item.customer_id,
            lead_id: item.primary_lead_id || null,
            duration_half_days: 2,
            visit_purpose: (item.reasons || []).slice(0, 3).join(', ') || 'Customer visit',
            allow_duplicate: allowDuplicate
        });
        if (!TripPlanIdentity.accept(token, withStop)) return;
        notify(I18n.t('Stop added'));
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner({ token });
        shouldPreview = Boolean(State.currentTripPlan?.stops?.length);
        if (shouldPreview) TripPlanningDraft.change(() => {});
    } catch (err) {
        console.error('Add stop error:', err);
        await handleTripError(err, 'Add stop');
    } finally {
        setTripBusy(false);
    }
    if (shouldPreview) {
        notify(I18n.t('Stop added. Updating the route preview; the route is not saved yet.'));
        await window.previewCurrentTripItinerary({ automatic: true });
    }
};
