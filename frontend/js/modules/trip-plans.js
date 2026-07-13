window.createTripPlanFromForm = async function() {
    const payload = { ...readTripPlanFormPayload(), status: 'Draft' };
    try {
        State.currentTripPlan = await ApiClient.createTripPlan(payload);
        populateTripPlanForm(State.currentTripPlan);
        notify('Trip plan created');
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner();
    } catch (err) {
        console.error('Create trip plan error:', err);
        alert('Error creating trip plan: ' + (err.message || 'Unknown error'));
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
        <button type="button" class="trip-plan-row ${State.currentTripPlan?.id === plan.id ? 'active' : ''}"
            onclick="selectTripPlan('${plan.id}')">
            <span>
                <strong>${escapeHtml(plan.title)}</strong>
                <small>${escapeHtml([plan.start_date, plan.end_date].filter(Boolean).join(' to ') || 'No dates')}</small>
            </span>
            <em>${plan.stop_count || 0}</em>
        </button>
    `).join('');
}

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
        notify('Stop added');
        State.tripCandidatePagination.offset = 0;
        await loadTripPlanner();
    } catch (err) {
        console.error('Add stop error:', err);
        alert('Error adding stop: ' + (err.message || 'Unknown error'));
    }
};

