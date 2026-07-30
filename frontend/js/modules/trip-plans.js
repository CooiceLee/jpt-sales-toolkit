window.createTripPlanFromForm = async function() {
    const payload = { ...readTripPlanFormPayload(), status: 'Draft' };
    try {
        State.currentTripPlan = await ApiClient.createTripPlan(payload);
        populateTripPlanForm(State.currentTripPlan);
        notify(I18n.t('Trip plan created'));
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner();
    } catch (err) {
        console.error('Create trip plan error:', err);
        alert(I18n.t('Error creating trip plan: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};

window.selectTripPlan = async function(planId) {
    try {
        State.currentTripPlan = await ApiClient.getTripPlan(planId);
        populateTripPlanForm(State.currentTripPlan);
        renderTripPlans();
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
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
        container.innerHTML = '<div class="empty-state compact">No saved plans</div>';
        return;
    }
    container.innerHTML = plans.map(plan => `
        <div class="trip-plan-row ${State.currentTripPlan?.id === plan.id ? 'active' : ''}">
            <button type="button" class="trip-plan-select" onclick="selectTripPlan('${plan.id}')">
                <span>
                    <strong>${escapeHtml(plan.title)}</strong>
                    <small>${escapeHtml([plan.start_date, plan.end_date].filter(Boolean).join(' to ') || 'No dates')}</small>
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
    const plan = (State.tripPlans || []).find(item => item.id === planId);
    if (!plan || !confirm(I18n.t('Archive trip plan “{title}”?', {
        title: plan.title || I18n.t('Untitled')
    }))) return;
    try {
        await ApiClient.archiveTripPlan(planId, rowVersion);
        if (State.currentTripPlan?.id === planId) State.currentTripPlan = null;
        notify(I18n.t('Trip plan archived'));
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner();
    } catch (err) {
        console.error('Archive trip plan error:', err);
        await handleTripError(err, 'Archive trip plan');
    }
};

window.addCandidateToCurrentPlan = async function(index) {
    const item = State.tripCandidates[index];
    if (!item) return;
    if (!State.currentTripPlan) {
        await createTripPlanFromForm();
    }
    if (!State.currentTripPlan?.id) return;

    try {
        State.currentTripPlan = await ApiClient.addTripStop(State.currentTripPlan.id, {
            customer_id: item.customer_id,
            lead_id: item.primary_lead_id || null,
            stay_days: 1,
            visit_purpose: (item.reasons || []).slice(0, 3).join(', ') || 'Customer visit'
        });
        notify(I18n.t('Stop added'));
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner();
    } catch (err) {
        console.error('Add stop error:', err);
        alert(I18n.t('Error adding stop: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};
