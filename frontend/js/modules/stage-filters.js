(function () {
    'use strict';

    function bindOnce(id, eventName, handler) {
        const element = document.getElementById(id);
        if (!element || element.dataset.stageFilterBound || typeof handler !== 'function') return;
        element.dataset.stageFilterBound = '1';
        element.addEventListener(eventName, handler);
    }

    function initFilterTabs(moduleId, loadFn) {
        const module = document.getElementById(moduleId);
        if (!module) return;
        const moduleKey = moduleId.replace('module-', '');

        module.querySelectorAll('.filter-tab').forEach(tab => {
            if (tab.dataset.filterTabBound) return;
            tab.dataset.filterTabBound = '1';
            tab.addEventListener('click', () => {
                module.querySelectorAll('.filter-tab').forEach(item => item.classList.remove('active'));
                tab.classList.add('active');
                State.currentFilters[moduleKey] = tab.dataset.filter;
                State.currentFilter = tab.dataset.filter;
                loadFn();
            });
        });
    }

    function initFilters() {
        bindOnce('filter-stage', 'change', loadHandler);
        bindOnce('map-stage-filter', 'change', loadReviewMap);
        bindOnce('map-outcome-filter', 'change', loadReviewMap);
        bindOnce('map-region-filter', 'change', loadReviewMap);
        bindOnce('map-quality-filter', 'change', () => {
            if (State.mapData) renderReviewMap(State.mapData);
        });
        bindOnce('review-period', 'change', applyReviewPeriod);
        bindOnce('review-date-from', 'change', loadDataReview);
        bindOnce('review-date-to', 'change', loadDataReview);
        bindOnce('review-region', 'change', loadDataReview);
        bindOnce('review-stage', 'change', loadDataReview);
        bindOnce('trip-candidate-region', 'change', window.resetTripPlannerFilters);
        bindOnce('trip-stage', 'change', window.resetTripPlannerFilters);
        window.FollowupFilterControls?.init();

        initFilterTabs('module-followup', loadFollowup);
        initFilterTabs('module-sampling', loadSampling);
        initFilterTabs('module-deal', loadDeal);
        initFilterTabs('module-fulfillment', loadFulfillment);
        initFilterTabs('module-aftersales', loadAftersales);
    }

    window.initFilters = initFilters;
})();
