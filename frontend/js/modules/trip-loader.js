window.resetTripPlannerFilters = async function() {
    State.tripCandidatePagination.offset = 0;
    await loadTripPlanner({ appendCandidates: false });
};

window.loadTripPlanner = async function(options = {}) {
    if (!options.force && window.TripBriefingDraft?.guard?.({ silent: Boolean(options.automatic) })) return;
    if (!options.force && window.TripVisitDraft?.guard?.({ silent: Boolean(options.automatic) })) return;
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
            notify(I18n.t('Could not load more candidates'));
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
            window.TripPlanningDraft?.hydrate?.(null);
        }
        renderTripPlans();
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
        renderTripMap();
    } else {
        console.error('Trip plans error:', plansResult.reason);
        setPanelError('trip-plan-list', 'Unable to load saved plans');
        renderCurrentTripPlan();
        window.TripPlannerModule?.renderVisitExecution(State.currentTripPlan);
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
    }
};

function initTripPlannerMap() {
    if (State.tripMap) return;
    const el = document.getElementById('trip-map');
    if (!el) return;
    State.tripMap = L.map('trip-map').setView([35, 20], 2);
    MapSupport.addTileLayer(State.tripMap, { containerId: 'trip-map', style: 'light' });
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
    root.querySelectorAll('button, input, select, textarea').forEach(control => {
        if (busy) {
            if (!control.disabled) {
                control.dataset.tripBusyDisabled = '1';
                control.disabled = true;
            }
        } else if (control.dataset.tripBusyDisabled === '1') {
            control.disabled = false;
            delete control.dataset.tripBusyDisabled;
        }
    });
}
