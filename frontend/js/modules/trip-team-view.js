/** Travel Team card: who is going, and where each of them starts and ends. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);

    function endpointLine(plan, member) {
        const from = member.origin_name_override
            || plan?.origin_name || t('Plan departure point');
        const to = member.destination_name_override
            || plan?.destination_name || t('Plan return point');
        return `${from} → ${to}`;
    }

    function renderMember(plan, member) {
        const total = plan?.itinerary_summary?.member_totals?.[member.user_id];
        const metrics = total ? [
            total.distance_km != null
                ? t('{count} km', {
                    count: Math.round(total.distance_km).toLocaleString('en-US'),
                }) : '',
            total.calculated_end_date
                ? t('back {date}', { date: total.calculated_end_date }) : '',
        ].filter(Boolean).join(' · ') : '';
        return `<li class="trip-team-member">
            <div>
                <strong>${h(member.display_name || member.user_id)}</strong>
                <small>${h(endpointLine(plan, member))}</small>
                ${metrics ? `<small class="trip-team-metrics">${h(metrics)}</small>` : ''}
            </div>
            <button type="button" class="btn btn-secondary btn-sm trip-team-remove"
                title="${h(t('Remove'))}" aria-label="${h(t('Remove'))}"
                onclick="TripTeamActions.remove('${h(member.user_id)}')">&times;</button>
        </li>`;
    }

    function addRow(plan) {
        const taken = new Set((plan?.members || []).map(item => item.user_id));
        const options = (plan?.available_members || [])
            .filter(item => !taken.has(item.user_id));
        if (!options.length) {
            return `<p class="trip-form-help">${h(t('Everybody on the team is already on this trip.'))}</p>`;
        }
        return `<div class="trip-team-add">
            <select class="form-input" id="trip-team-add-user"
                aria-label="${h(t('Team member to add'))}">
                ${options.map(item => `<option value="${h(item.user_id)}">${
                    h(item.display_name || item.user_id)}</option>`).join('')}
            </select>
            <button type="button" class="btn btn-primary btn-sm"
                onclick="TripTeamActions.add()">${h(t('Add to trip'))}</button>
        </div>`;
    }

    function render(plan, target = document.getElementById('trip-team-body')) {
        const panel = document.getElementById('trip-team-panel');
        if (!target || !panel) return;
        // The card belongs to team planning. A single-traveller plan has no team
        // to show, so it is not there at all rather than shown empty.
        panel.hidden = plan?.planning_mode !== 'team';
        if (panel.hidden) return;
        const members = plan?.members || [];
        target.innerHTML = `
            ${members.length
                ? `<ul class="trip-team-list">${members
                    .map(member => renderMember(plan, member)).join('')}</ul>`
                : `<p class="trip-form-help">${h(t(
                    'Add the people travelling before previewing the route.'
                ))}</p>`}
            ${addRow(plan)}
        `;
    }

    window.TripTeamView = Object.freeze({ render, renderMember, endpointLine });
})();
