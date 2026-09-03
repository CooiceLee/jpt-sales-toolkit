window.resetTripPlannerFilters = async function() {
    // This starts a request of its own, which is what makes whatever page was
    // in flight for the previous filter too old to be shown.
    await loadTripCandidates({ append: false, offset: 0 });
};

/** Load the customers on offer. Nothing here decides which plan is on screen.

Paging and filtering the candidate list is its own concern. Reading it as a
reason to reload the plan too would let scrolling the list overrule a plan the
reader had just opened, because the reload would claim the screen for whichever
plan it happened to find.
*/
window.loadTripCandidates = async function(options = {}) {
    const append = !!options.append;
    // The page asked for. Nothing is written to the pagination until the answer
    // for that page arrives, so a request that fails leaves the list where it
    // was rather than skipping past the page it could not fetch.
    const offset = options.offset ?? (append
        ? State.tripCandidatePagination.offset || 0 : 0);
    const filters = { ...getTripFilters(), offset };
    // A caller that already claimed the list passes its request in; taking
    // another here would make its own answer look newer than itself.
    const request = options.request ?? TripCandidateRequests.start();
    initTripPlannerMap();
    if (!append) setPanelLoading('trip-candidate-list', 'Loading candidates...');
    let candidateData;
    try {
        candidateData = await ApiClient.getTripCandidates(filters);
    } catch (error) {
        console.error('Trip candidates error:', error);
        if (!TripCandidateRequests.mayWrite(request)) return false;
        if (append) {
            notify(I18n.t('Could not load more candidates'));
        } else {
            State.tripCandidates = [];
            renderTripMap();
            setPanelError('trip-candidate-list', 'Unable to load candidates');
        }
        return false;
    }
    // An answer to a question the reader has since changed describes customers
    // they are no longer asking about, and appending it would mix the two.
    if (!TripCandidateRequests.mayWrite(request)) return false;
    State.tripCandidatePagination = {
        ...State.tripCandidatePagination,
        ...((candidateData || {}).pagination || {}),
        offset,
    };
    const page = (candidateData || {}).candidates || [];
    State.tripCandidates = append ? [...State.tripCandidates, ...page] : page;
    renderTripCandidates();
    renderTripMap();
    return true;
};

/** Reload the planner. Returns false when unsaved work stopped it. */
window.loadTripPlanner = async function(options = {}) {
    if (!options.force && window.TripBriefingDraft?.guard?.({ silent: Boolean(options.automatic) })) return false;
    if (!options.force && window.TripVisitDraft?.guard?.({ silent: Boolean(options.automatic) })) return false;
    // A reload that finishes something the reader started earlier belongs to
    // that action and carries its number. Taking a fresh one here would make
    // the tail of an old action newer than whatever the reader chose since,
    // and the old action would win.
    const token = options.token ?? TripPlanIdentity.intend();
    if (!TripPlanIdentity.isCurrent(token)) return false;
    setPanelLoading('trip-plan-list', 'Loading plans...');

    const [, plansResult] = await Promise.allSettled([
        loadTripCandidates({ append: !!options.appendCandidates }),
        ApiClient.listTripPlans()
    ]);

    if (plansResult.status === 'fulfilled') {
        State.tripPlans = plansResult.value || [];
        if (State.tripPlans.length) {
            const selectedPlanId = State.currentTripPlan?.id;
            const targetPlan = State.tripPlans.find(plan => plan.id === selectedPlanId) || State.tripPlans[0];
            try {
                const plan = await ApiClient.getTripPlan(targetPlan.id);
                // A reload started before the reader opened another plan must
                // not put them back on the one they left.
                if (!TripPlanIdentity.accept(token, plan)) return false;
                populateTripPlanForm(State.currentTripPlan);
            } catch (err) {
                console.error('Load selected trip plan error:', err);
                TripPlanIdentity.clear(token);
            }
        } else {
            TripPlanIdentity.clear(token);
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
    return true;
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
