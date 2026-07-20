(function () {
    'use strict';

    function initFilterTabs(moduleId, loadFn) {
        const module = document.getElementById(moduleId);
        if (!module) return;
        const moduleKey = moduleId.replace('module-', '');

        module.querySelectorAll('.filter-tab').forEach(tab => {
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
        document.getElementById('filter-stage')?.addEventListener('change', loadHandler);
        document.getElementById('map-stage-filter')?.addEventListener('change', loadReviewMap);
        document.getElementById('map-outcome-filter')?.addEventListener('change', loadReviewMap);
        document.getElementById('map-region-filter')?.addEventListener('change', loadReviewMap);
        document.getElementById('map-quality-filter')?.addEventListener('change', () => {
            if (State.mapData) renderReviewMap(State.mapData);
        });
        document.getElementById('review-period')?.addEventListener('change', applyReviewPeriod);
        document.getElementById('review-date-from')?.addEventListener('change', loadDataReview);
        document.getElementById('review-date-to')?.addEventListener('change', loadDataReview);
        document.getElementById('review-region')?.addEventListener('change', loadDataReview);
        document.getElementById('review-stage')?.addEventListener('change', loadDataReview);
        document.getElementById('trip-region')?.addEventListener('change', window.resetTripPlannerFilters);
        document.getElementById('trip-stage')?.addEventListener('change', window.resetTripPlannerFilters);
        window.FollowupFilterControls?.init();

        initFilterTabs('module-followup', loadFollowup);
        initFilterTabs('module-sampling', loadSampling);
        initFilterTabs('module-deal', loadDeal);
        initFilterTabs('module-fulfillment', loadFulfillment);
        initFilterTabs('module-aftersales', loadAftersales);
    }

    window.initFilters = initFilters;
})();
