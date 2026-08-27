/** Proposed times for the customer visits with none agreed. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    let state = null;

    function memberNames(plan, userIds) {
        const names = (userIds || []).map(id =>
            window.TripTeamJourneys?.memberName?.(plan, id) || id);
        return names.length ? names.join(' · ') : t('Whole travel team');
    }

    function impact(item) {
        return [
            item.added_travel_hours
                ? t('+{count} h travel', { count: item.added_travel_hours }) : '',
            item.added_distance_km
                ? t('+{count} km', { count: Math.round(item.added_distance_km) }) : '',
        ].filter(Boolean).join(' · ');
    }

    function renderItem(plan, item) {
        const who = memberNames(plan, item.participants);
        if (!item.date) {
            return `<li class="trip-suggestion is-none">
                <div><strong>${h(item.label || item.stop_id)}</strong>
                    <small>${h(who)}</small>
                    <small>${h(t('No workable time in this trip'))}</small></div>
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripBriefingActions.open('${h(item.stop_id)}')">${
                    h(t('Arrange manually'))}</button>
            </li>`;
        }
        const period = t(item.period === 'PM' ? 'Afternoon (PM)' : 'Morning (AM)');
        return `<li class="trip-suggestion">
            <div><strong>${h(item.label || item.stop_id)}</strong>
                <small>${h(who)}</small>
                <small>${h(`${item.date} · ${period}`)}${
                    impact(item) ? ` · ${h(impact(item))}` : ''}</small></div>
            <button type="button" class="btn btn-primary btn-sm"
                onclick="TripFlexibleSuggestions.apply('${h(item.stop_id)}')">${
                h(t('Apply'))}</button>
        </li>`;
    }

    function render(plan) {
        const panel = document.getElementById('trip-suggestions-panel');
        const body = document.getElementById('trip-suggestions-body');
        if (!panel || !body) return;
        panel.hidden = plan?.planning_mode !== 'team';
        if (panel.hidden) {
            state = null;
            body.innerHTML = '';
            return;
        }
        if (!state || state.planId !== plan?.id) {
            body.innerHTML = `<p class="trip-form-help">${h(t(
                'Ask for a suggested time for the visits with none agreed.'
            ))}</p>`;
            return;
        }
        body.innerHTML = state.suggestions.length
            ? `<ul class="trip-suggestion-list">${state.suggestions
                .map(item => renderItem(plan, item)).join('')}</ul>`
            : `<p class="trip-form-help">${h(t(
                'Every customer visit already has a time.'
            ))}</p>`;
    }

    async function load() {
        const plan = State.currentTripPlan;
        if (!plan?.id) return;
        try {
            const result = await ApiClient.getTripFlexibleSuggestions(plan.id);
            state = {
                planId: plan.id,
                planVersion: result.plan_row_version,
                suggestions: result.suggestions || [],
            };
        } catch (error) {
            state = null;
            notify(error?.message
                || t('Could not work out suggested times'));
        }
        render(State.currentTripPlan);
    }

    /**
     * Take one proposal.
     *
     * Each suggestion after the first was worked out with the ones before it
     * already in place, so the rest of the list stops meaning anything the
     * moment one is taken. It is discarded and asked for again rather than
     * patched, which is also why the plan's version goes with the change.
     */
    async function apply(stopId) {
        const item = (state?.suggestions || []).find(
            row => row.stop_id === stopId);
        const stop = (State.currentTripPlan?.stops || []).find(
            row => row.id === stopId);
        if (!item?.date || !stop) return;
        try {
            const plan = await ApiClient.updateTripStop(
                State.currentTripPlan.id, stopId, {
                    planned_date: item.date,
                    planned_start_period: item.period,
                    schedule_locked: false,
                    // A decision, not a calculation: this is what makes the
                    // time hold its place in the next run.
                    planned_time_accepted: true,
                    row_version: stop.row_version,
                    plan_row_version: state.planVersion,
                });
            State.currentTripPlan = plan;
            state = null;
            window.renderCurrentTripPlan?.();
            window.TripScheduleView?.renderPlan?.(plan);
            window.renderTripMap?.();
            await load();
        } catch (error) {
            state = null;
            render(State.currentTripPlan);
            notify(error?.message
                || t('The plan has changed. Look at the suggestions again.'));
            window.loadTripPlanner?.();
        }
    }

    window.TripFlexibleSuggestions = Object.freeze({ render, load, apply });
})();
