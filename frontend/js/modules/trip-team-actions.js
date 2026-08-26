/** Adding and removing the people on a trip. */
(function() {
    const t = (key, params = {}) => I18n.t(key, params);

    function currentPlanId() {
        return window.State?.currentTripPlan?.id || '';
    }

    async function apply(action) {
        const planId = currentPlanId();
        if (!planId) return;
        try {
            const plan = await action(planId);
            if (!plan) return;
            State.currentTripPlan = plan;
            window.renderCurrentTripPlan?.();
            window.TripScheduleView?.renderPlan?.(plan);
            window.renderTripMap?.();
        } catch (error) {
            window.showToast?.(error?.message || t('Could not update the travel team'), 'error');
        }
    }

    async function add() {
        const select = document.getElementById('trip-team-add-user');
        const userId = select?.value;
        if (!userId) return;
        await apply(planId => API.setTripMember(planId, { user_id: userId }));
    }

    async function remove(userId) {
        if (!userId) return;
        // Removing somebody takes the route worked out for them with it, so this
        // is asked before it happens rather than reported after.
        const confirmed = window.confirm(t(
            'Remove this person from the trip? The route planned for them is removed as well.'
        ));
        if (!confirmed) return;
        await apply(planId => API.removeTripMember(planId, userId));
    }

    window.TripTeamActions = Object.freeze({ add, remove });
})();
