/** Risk bar for team planning, rendered from summary.risks only. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);

    // The backend says what happened as a kind plus its values; the sentence is
    // built here so it can be translated. No risk is decided in the frontend.
    const SENTENCES = Object.freeze({
        member_double_booked: risk => t(
            '{member} has two customer visits booked for {date} {period}. Change who attends, or confirm another member covers one of them.',
            risk
        ),
        parallel_visits_unassigned: risk => t(
            '{count} visits are booked for {date} {period} with nobody assigned. Choose who attends each one.',
            risk
        ),
        participant_not_in_trip_team: risk => t(
            'A visit names people who are not on this trip. Add them to the travel team, or change who attends.',
            risk
        ),
        cannot_reach_booked_visit: risk => t(
            '{member} is not expected to reach the visit booked for {date} {period}. Confirm the travel, or move the appointment.',
            risk
        ),
        planned_visit_moved: risk => t(
            '{stop} was planned for {plannedDate} but moved to {date} {period}: the team cannot get there earlier. Confirm the new time, or change the plan.',
            risk
        ),
        member_return_overrun: risk => t(
            '{member} is expected back on {date}, after the planned end of the trip on {deadline}. Confirm the return arrangement.',
            risk
        ),
    });

    function memberName(plan, userId) {
        if (!userId) return t('Unassigned');
        const member = (plan?.members || []).find(item => item.user_id === userId);
        return member?.display_name || userId;
    }

    function stopName(plan, stopId) {
        const stop = (plan?.stops || []).find(item => item.id === stopId);
        return stop?.customer_name || stop?.location_name || t('This visit');
    }

    function describe(plan, risk) {
        const build = SENTENCES[risk?.kind];
        if (!build) return '';
        return build({
            ...risk,
            member: memberName(plan, risk.member_id || risk.user_id),
            stop: stopName(plan, risk.stop_id),
            plannedDate: risk.planned_date,
            period: t(risk.period === 'PM' ? 'Afternoon (PM)' : 'Morning (AM)'),
            count: risk.visit_count || (risk.stop_ids || []).length,
        });
    }

    function lines(plan) {
        const risks = plan?.itinerary_summary?.risks || [];
        return risks.map(risk => describe(plan, risk)).filter(Boolean);
    }

    function render(plan, target = document.getElementById('trip-risk-bar')) {
        if (!target) return;
        const messages = lines(plan);
        if (!messages.length) {
            target.hidden = true;
            target.innerHTML = '';
            return;
        }
        target.hidden = false;
        target.innerHTML = `
            <button type="button" class="trip-risk-summary" aria-expanded="false"
                onclick="TripTeamRisks.toggle()">
                <span class="trip-risk-icon" aria-hidden="true">!</span>
                <strong>${h(t('{count} schedule risks', { count: messages.length }))}</strong>
                <span class="trip-risk-caret" aria-hidden="true">▾</span>
            </button>
            <ul class="trip-risk-list" hidden>
                ${messages.map(message => `<li>${h(message)}</li>`).join('')}
            </ul>
        `;
    }

    function toggle() {
        const target = document.getElementById('trip-risk-bar');
        const list = target?.querySelector('.trip-risk-list');
        const button = target?.querySelector('.trip-risk-summary');
        if (!list || !button) return;
        list.hidden = !list.hidden;
        button.setAttribute('aria-expanded', list.hidden ? 'false' : 'true');
    }

    window.TripTeamRisks = Object.freeze({ render, lines, describe, toggle });
})();
