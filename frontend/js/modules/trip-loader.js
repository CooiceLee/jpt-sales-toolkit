window.resetTripPlannerFilters = async function() {
    State.tripCandidatePagination.offset = 0;
    await loadTripPlanner({ appendCandidates: false });
};

window.loadTripPlanner = async function(options = {}) {
    const appendCandidates = !!options.appendCandidates;
    initTripPlannerMap();
    if (!appendCandidates) {
        setPanelLoading('trip-candidate-list', 'Loading candidates...');
    }
    setPanelLoading('trip-plan-list', 'Loading plans...');

    const [candidateResult, plansResult] = await Promise.allSettled([
        ApiClient.getTripCandidates(getTripFilters()),
        ApiClient.listTripPlans()
    ]);

    if (candidateResult.status === 'fulfilled') {
        const candidateData = candidateResult.value || {};
        State.tripCandidatePagination = {
            ...State.tripCandidatePagination,
            ...(candidateData.pagination || {})
        };
        const page = candidateData.candidates || [];
        State.tripCandidates = appendCandidates ? [...State.tripCandidates, ...page] : page;
        renderTripCandidates();
        renderTripMap();
    } else {
        console.error('Trip candidates error:', candidateResult.reason);
        if (!appendCandidates) {
            State.tripCandidates = [];
            renderTripMap();
            setPanelError('trip-candidate-list', 'Unable to load candidates');
        } else {
            notify('Could not load more candidates');
        }
    }

    if (plansResult.status === 'fulfilled') {
        State.tripPlans = plansResult.value || [];
        if (State.tripPlans.length) {
            const selectedPlanId = State.currentTripPlan?.id;
            const targetPlan = State.tripPlans.find(plan => plan.id === selectedPlanId) || State.tripPlans[0];
            try {
                State.currentTripPlan = await ApiClient.getTripPlan(targetPlan.id);
                populateTripPlanForm(State.currentTripPlan);
            } catch (err) {
                console.error('Load selected trip plan error:', err);
                State.currentTripPlan = null;
            }
        } else {
            State.currentTripPlan = null;
        }
        renderTripPlans();
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
        renderTripMap();
    } else {
        console.error('Trip plans error:', plansResult.reason);
        setPanelError('trip-plan-list', 'Unable to load saved plans');
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
    }
};

function initTripPlannerMap() {
    if (State.tripMap) return;
    const el = document.getElementById('trip-map');
    if (!el) return;
    State.tripMap = L.map('trip-map').setView([35, 20], 2);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap, CARTO'
    }).addTo(State.tripMap);
    State.tripMapLayer = L.layerGroup().addTo(State.tripMap);
}

function destroyTripPlannerMap() {
    if (!State.tripMap) return;
    State.tripMap.remove();
    State.tripMap = null;
    State.tripMapLayer = null;
}

function setTripBusy(busy) {
    State.tripBusy = busy;
    const root = document.getElementById('module-trip-planner');
    if (!root) return;
    root.classList.toggle('trip-busy', busy);
    root.querySelectorAll('button').forEach(button => {
        if (busy) {
            if (!button.disabled) {
                button.dataset.tripBusyDisabled = '1';
                button.disabled = true;
            }
        } else if (button.dataset.tripBusyDisabled === '1') {
            button.disabled = false;
            delete button.dataset.tripBusyDisabled;
        }
    });
}

