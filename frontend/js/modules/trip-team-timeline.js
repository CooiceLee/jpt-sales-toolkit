/** Team timeline: who is where, half-day by half-day. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const slotOf = item => `${item.date || ''}|${item.period === 'PM' ? 'PM' : 'AM'}`;

    function memberName(plan, userId) {
        const member = (plan?.members || []).find(item => item.user_id === userId);
        return member?.display_name || userId || t('Unassigned');
    }

    /**
     * One line per thing that happens, with everybody who is on it.
     *
     * Colleagues travelling together are one line, not one per person: the team
     * arrangement is what the plan means, and repeating it per member reads as
     * separate visits.
     */
    function groupSlot(items, plan) {
        const merged = new Map();
        items.forEach(item => {
            const key = `${item.item_type}|${item.source_id}|${item.title}`;
            const entry = merged.get(key) || {
                ...item, members: [], unresolved: false,
            };
            if (item.member_id) entry.members.push(memberName(plan, item.member_id));
            if (item.inbound_travel_resolved === false) entry.unresolved = true;
            merged.set(key, entry);
        });
        return [...merged.values()].sort((left, right) =>
            String(left.item_type).localeCompare(String(right.item_type))
            || String(left.title).localeCompare(String(right.title)));
    }

    function renderEntry(entry) {
        const isLeg = entry.item_type === 'leg';
        const stopId = !isLeg ? entry.source_id : '';
        const who = entry.members.length
            ? entry.members.join(' · ') : t('Unassigned');
        return `<button type="button"
            class="trip-team-entry is-${h(isLeg ? 'leg' : entry.item_type)}${
                entry.unresolved ? ' is-unresolved' : ''}"
            ${stopId ? `onclick="TripBriefingActions.open('${h(stopId)}')"` : 'disabled'}>
            <span class="trip-team-entry-who">${h(who)}</span>
            <strong>${h(entry.title || entry.source_id)}${
                entry.half_day_count > 1
                    ? ` · ${t('Half-day {index} of {count}', {
                        index: entry.half_day_index, count: entry.half_day_count,
                    })}` : ''}</strong>
            ${entry.unresolved
                ? `<em>${h(t('Travel to this visit is not worked out'))}</em>` : ''}
        </button>`;
    }

    function renderSlot(slot, entries) {
        const [date, period] = slot.split('|');
        return `<section class="trip-team-slot">
            <h4>${h(date)} · ${h(t(period === 'PM' ? 'Afternoon (PM)' : 'Morning (AM)'))}</h4>
            <div class="trip-team-slot-body">${entries.map(renderEntry).join('')}</div>
        </section>`;
    }

    function incompleteNotice(plan) {
        // A member whose position the plan cannot work out has no route to draw.
        // Saying so is the honest thing; drawing a line anyway would be a guess.
        const totals = plan?.itinerary_summary?.member_totals || {};
        const stranded = Object.entries(totals)
            .filter(([, total]) => total?.route_complete === false)
            .map(([userId]) => memberName(plan, userId));
        if (!stranded.length) return '';
        return `<div class="trip-team-incomplete">${h(t(
            'The route is not complete for {members}. Their travel is left out until who attends what is settled.',
            { members: stranded.join(' · ') }
        ))}</div>`;
    }

    function render(plan, target = document.getElementById('trip-schedule-list')) {
        if (!target) return;
        const items = plan?.schedule_items || [];
        if (!items.length) {
            target.innerHTML = `<div class="empty-state compact">${h(t(
                'Save or preview a route to create the team timeline.'
            ))}</div>`;
            return;
        }
        const slots = new Map();
        items.forEach(item => {
            const key = slotOf(item);
            slots.set(key, [...(slots.get(key) || []), item]);
        });
        const ordered = [...slots.keys()].sort();
        target.innerHTML = incompleteNotice(plan) + ordered
            .map(slot => renderSlot(slot, groupSlot(slots.get(slot), plan)))
            .join('');
    }

    function renderPlan(plan) {
        render(plan);
        window.TripTeamRisks?.render?.(plan);
        const status = document.getElementById('trip-schedule-status');
        if (status) {
            status.textContent = t('{count} people travelling', {
                count: (plan?.members || []).length,
            });
        }
    }

    window.TripTeamTimeline = Object.freeze({
        render, renderPlan, groupSlot, incompleteNotice,
    });
})();
