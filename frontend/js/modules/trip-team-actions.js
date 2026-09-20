/** Adding and removing the people on a trip. */
(function() {
    const t = (key, params = {}) => I18n.t(key, params);

    function currentPlanId() {
        // State is declared with const at the top level of app.js, so it is not
        // a property of window: reading it through window gives undefined and
        // every action here silently does nothing.
        return State.currentTripPlan?.id || '';
    }

    /** The plan and the screen this change belongs to, taken when it was asked
     * for.
     *
     * Read at the front of the queue instead, a change made on plan A and
     * queued behind something slow is sent to whichever plan the reader has
     * opened by the time it runs - and its answer then claims the screen that
     * other plan is on. Both the address and the screen are claimed here, at
     * the moment the reader acts.
     */
    function claim() {
        const planId = currentPlanId();
        return planId ? { planId, token: TripPlanIdentity.intend() } : null;
    }

    async function apply(action, held) {
        const claimed = held || claim();
        if (!claimed) return null;
        const { planId, token } = claimed;
        try {
            const plan = await action(planId);
            if (!plan) return null;
            // The reader has opened something else since: the write happened on
            // the plan they asked for, and their screen is not ours to redraw.
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
        // Claimed now, not when the queue gets to it: see claim().
        const held = claim();
        if (!held) return;
        // One change at a time. Two dates sent together come back in whatever
        // order the server answers, and the earlier answer would overwrite the
        // later change while the box goes on showing the newer date.
        const done = await TripTeamQueue.run(async () => {
            if (field) field.disabled = true;
            return apply(planId => ApiClient.setTripMember(planId, {
                user_id: userId, departure_date: value || null,
                row_version: before?.row_version || null,
            }), held);
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

    // The editor collects the two points; getting them saved, and the answer
    // applied to the plan on screen, is the same path every other member change
    // takes - one write at a time, newest plan wins, panel redrawn from it.
    async function saveEndpoints(userId, fields) {
        if (!userId) return false;
        const before = memberOf(userId);
        const held = claim();
        if (!held) return false;
        const name = nameOf(userId);
        // The editor that sent this is frozen until the answer comes back: it
        // is the one being written from, and typing into it meanwhile would be
        // overwritten by the redraw the answer brings.
        window.TripTeamEndpoints?.setBusy?.(userId, true);
        const plan = await TripTeamQueue.run(() => apply(
            planId => ApiClient.setTripMember(planId, {
                user_id: userId, ...fields,
                row_version: before?.row_version || null,
            }), held
        ));
        window.TripTeamEndpoints?.setBusy?.(userId, false);
        if (!plan) return false;
        // Each end is its own answer: one can follow the plan while the other
        // does not, and one sentence for both said the wrong thing about one.
        notify([
            fields.origin_name_override
                ? t('{name} leaves from {place}', {
                    name, place: fields.origin_name_override })
                : t("{name} leaves from the plan's departure point", { name }),
            fields.destination_name_override
                ? t('{name} returns to {place}', {
                    name, place: fields.destination_name_override })
                : t("{name} returns to the plan's return point", { name }),
        ].join(' · '));
        return true;
    }

    window.TripTeamActions = Object.freeze({
        add, remove, departureChanged, saveEndpoints, memberOf,
    });
})();
