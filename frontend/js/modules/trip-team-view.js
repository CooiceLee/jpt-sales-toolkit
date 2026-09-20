/** Travel Team card: who is going, and where each of them starts and ends. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);

    function endpointLine(plan, member) {
        const from = member.origin_name_override
            || plan?.origin_name || t('Plan departure point');
        const to = member.destination_name_override
            || plan?.destination_name || t('Plan return point');
        // Whose points these are decides whether the plan's own departure field
        // applies to this person at all, and that is what the card was not
        // saying: the same two names are shown either way.
        const own = member.origin_lat_override != null
            || member.destination_lat_override != null;
        return `${from} → ${to}${own ? ` · ${t('own places')}` : ''}`;
    }

    // Outside the plan's own dates the calculation passes the date over, so the
    // field says that where it was typed - waiting for a recalculation to
    // mention it is why somebody set the same date twice and saw nothing move.
    function departureNote(plan, member) {
        const day = member.departure_date || '';
        if (!day) return '';
        if (plan?.start_date && day < plan.start_date) {
            return t('Before the trip starts on {date}; the trip cannot begin earlier.',
                { date: plan.start_date });
        }
        if (plan?.end_date && day > plan.end_date) {
            return t('After the trip ends on {date}.', { date: plan.end_date });
        }
        return '';
    }

    function renderMember(plan, member) {
        const total = plan?.itinerary_summary?.member_totals?.[member.user_id];
        // Nobody on no visits has no journey, so "0 km · back 15 Sep" is a
        // calculated placeholder standing where a fact should be - and it
        // contradicts the line underneath saying they have no trip at all.
        const travels = (window.TripTeamItinerary?.stops?.(plan, member.user_id)
            || []).length > 0;
        const metrics = total && travels ? [
            total.distance_km != null
                ? t('{count} km', {
                    count: Math.round(total.distance_km).toLocaleString('en-US'),
                }) : '',
            total.calculated_end_date
                ? t('back {date}', { date: total.calculated_end_date }) : '',
        ].filter(Boolean).join(' · ') : '';
        return `<li class="trip-team-member">
            <div>
                <strong data-business>${h(member.display_name || member.user_id)}</strong>
                <small title="${h(endpointLine(plan, member))}">${
                    h(endpointLine(plan, member))}</small>
                ${metrics ? `<small class="trip-team-metrics">${h(metrics)}</small>` : ''}
            </div>
            <label class="trip-team-departure">
                <span>${h(t('Leaves on'))}</span>
                <input type="date" class="form-input"
                    id="trip-team-departure-${h(member.user_id)}"
                    value="${h(member.departure_date || '')}"
                    onchange="TripTeamActions.departureChanged('${h(member.user_id)}', this.value)"
                    title="${h(t('Empty means this member leaves with the team.'))}">
            </label>
            ${departureNote(plan, member)
                ? `<span class="trip-team-departure-note">${
                    h(departureNote(plan, member))}
                    <button type="button" class="btn btn-text btn-sm"
                        onclick="TripTeamView.showPlanDates()">${
                        h(t('Change the trip dates'))}</button></span>` : ''}
            <button type="button" class="btn btn-text btn-sm trip-team-endpoint-open"
                onclick="TripTeamEndpoints.toggle('${h(member.user_id)}')">${
                h(t('Change places'))}</button>
            <button type="button" class="btn btn-secondary btn-sm trip-team-remove"
                title="${h(t('Remove'))}" aria-label="${h(t('Remove'))}"
                onclick="TripTeamActions.remove('${h(member.user_id)}')">&times;</button>
            ${window.TripTeamItinerary?.render?.(plan, member) || ''}
            <div class="trip-team-endpoints" id="trip-team-endpoints-${h(member.user_id)}" hidden></div>
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
                ${options.map(item => `<option value="${h(item.user_id)}" data-business>${
                    h(item.display_name || item.user_id)}</option>`).join('')}
            </select>
            <button type="button" class="btn btn-primary btn-sm"
                onclick="TripTeamActions.add()">${h(t('Add to trip'))}</button>
        </div>`;
    }

    function render(plan, target = document.getElementById('trip-team-body')) {
        const panel = document.getElementById('trip-team-panel');
        if (!target || !panel) return;
        // Somebody may be part-way through editing one member's places. The
        // card is rebuilt from scratch here - by their own save, by another
        // member's, by a route calculation - so what they typed is taken out
        // first and put back afterwards rather than quietly thrown away.
        const held = window.TripTeamEndpoints?.capture?.();
        // The card belongs to team planning. A single-traveller plan has no team
        // to show, so it is not there at all rather than shown empty.
        panel.hidden = !plan?.id;
        if (panel.hidden) return;
        const members = plan?.members || [];
        target.innerHTML = `
            ${members.length
                ? `<p class="trip-team-count">${h(t('{count} people travelling', {
                    count: members.length,
                }))}</p><ul class="trip-team-list">${members
                    .map(member => renderMember(plan, member)).join('')}</ul>`
                : `<p class="trip-form-help">${h(t(
                    'Add the people travelling before previewing the route.'
                ))}</p>`}
            ${addRow(plan)}
        `;
        if (held) window.TripTeamEndpoints?.restore?.(held);
    }

    // The date that has to move is the plan's, and it is in the other card.
    // Saying "this will not take effect" without a way to the thing that would
    // make it take effect leaves the reader to hunt for it.
    function showPlanDates() {
        const field = document.getElementById('trip-start-date');
        if (!field) return;
        field.scrollIntoView({ block: 'center', behavior: 'smooth' });
        field.focus({ preventScroll: true });
    }

    window.TripTeamView = Object.freeze({
        render, renderMember, endpointLine, showPlanDates,
    });
})();
