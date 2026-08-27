/** Adding and removing the people on a trip. */
(function() {
    const t = (key, params = {}) => I18n.t(key, params);

    function currentPlanId() {
        return window.State?.currentTripPlan?.id || '';
    }

    async function apply(action) {
        const planId = currentPlanId();
        if (!planId) return null;
        try {
            const plan = await action(planId);
            if (!plan) return null;
            State.currentTripPlan = plan;
            window.renderCurrentTripPlan?.();
            window.TripScheduleView?.renderPlan?.(plan);
            window.renderTripMap?.();
            return plan;
        } catch (error) {
            console.error('Travel team update error:', error);
            notify(t(error?.message || 'Could not update the travel team'));
            return null;
        }
    }

    async function add() {
        const select = document.getElementById('trip-team-add-user');
        const userId = select?.value;
        if (!userId) return;
        // Say who joined by name: the confirmation is the point of pressing the
        // button, and a list that silently grew by one row is not one.
        const name = select.options[select.selectedIndex]?.text || userId;
        const plan = await apply(
            planId => ApiClient.setTripMember(planId, { user_id: userId })
        );
        if (plan) notify(t('{name} joined the trip', { name }));
    }

    async function remove(userId) {
        if (!userId) return;
        // Removing somebody takes the route worked out for them with it, so this
        // is asked before it happens rather than reported after.
        const confirmed = window.confirm(t(
            'Remove this person from the trip? The route planned for them is removed as well.'
        ));
        if (!confirmed) return;
        const plan = await apply(
            planId => ApiClient.removeTripMember(planId, userId)
        );
        if (plan) notify(t('Removed from the trip'));
    }

    window.TripTeamActions = Object.freeze({ add, remove });
})();
