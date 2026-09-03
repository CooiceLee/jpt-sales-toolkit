/** Adding and removing the people on a trip. */
(function() {
    const t = (key, params = {}) => I18n.t(key, params);

    function currentPlanId() {
        // State is declared with const at the top level of app.js, so it is not
        // a property of window: reading it through window gives undefined and
        // every action here silently does nothing.
        return State.currentTripPlan?.id || '';
    }

    async function apply(action) {
        const planId = currentPlanId();
        if (!planId) return null;
        const token = TripPlanIdentity.intend();
        try {
            const plan = await action(planId);
            if (!plan) return null;
            if (!TripPlanIdentity.accept(token, plan)) return null;
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

    async function departureChanged(userId, value) {
        if (!userId) return;
        const before = memberOf(userId);
        const field = document.getElementById(`trip-team-departure-${userId}`);
        // One change at a time. Two dates sent together come back in whatever
        // order the server answers, and the earlier answer would overwrite the
        // later change while the box goes on showing the newer date.
        const done = await TripTeamQueue.run(async () => {
            if (field) field.disabled = true;
            return apply(planId => ApiClient.setTripMember(planId, {
                user_id: userId, departure_date: value || null,
                row_version: before?.row_version || null,
            }));
        });
        if (field) field.disabled = false;
        if (!done) {
            // The save did not happen, so the box must stop claiming it did.
            if (field) field.value = before?.departure_date || '';
            return;
        }
        notify(value
            ? t('{name} now leaves on {date}', {
                name: nameOf(userId), date: value })
            : t('{name} now leaves with the team', { name: nameOf(userId) }));
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

    function memberOf(userId) {
        return (State.currentTripPlan?.members || [])
            .find(item => item.user_id === userId) || null;
    }

    function nameOf(userId) {
        return memberOf(userId)?.display_name || userId;
    }

    window.TripTeamActions = Object.freeze({ add, remove, departureChanged });
})();
