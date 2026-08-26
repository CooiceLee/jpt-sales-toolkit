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
     * What makes two members' items the same thing.
     *
     * For a journey that is the same way of travelling as well as the same two
     * places: colleagues who drive and take a train between the same cities are
     * not travelling together, and merging them would claim they are.
     */
    function identityOf(item) {
        const base = `${item.item_type}|${item.source_id}|${item.title}`;
        return item.item_type === 'leg'
            ? `${base}|${item.selected_mode || ''}` : base;
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
            const key = identityOf(item);
            const entry = merged.get(key) || {
                ...item, members: [], unresolved: false,
            };
            if (item.member_id) {
                entry.members.push(memberName(plan, item.member_id));
                entry.memberIds = [...(entry.memberIds || []), item.member_id];
            }
            if (item.inbound_travel_resolved === false) entry.unresolved = true;
            // A shared event sits where its earliest attendee puts it, so the
            // order within a half-day follows the journeys that led to it.
            entry.order = Math.min(
                entry.order ?? Number.MAX_SAFE_INTEGER,
                item.lane_order ?? Number.MAX_SAFE_INTEGER
            );
            merged.set(key, entry);
        });
        return [...merged.values()].sort((left, right) =>
            left.order - right.order
            || String(left.item_type).localeCompare(String(right.item_type))
            || String(left.title).localeCompare(String(right.title)));
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
            .map(slot => TripTeamTimelineView.renderSlot(
                slot, groupSlot(slots.get(slot), plan).map(entry => ({
                    ...entry,
                    commitment: TripTeamTimelineView.commitment(plan, entry),
                }))))
            .join('');
    }

    function renderPlan(plan) {
        render(plan);
        window.TripTeamRisks?.render?.(plan);
        window.TripFlexibleSuggestions?.render?.(plan);
        const status = document.getElementById('trip-schedule-status');
        if (status) {
            status.textContent = t('{count} people travelling', {
                count: (plan?.members || []).length,
            });
        }
    }

    window.TripTeamTimeline = Object.freeze({
        render, renderPlan, groupSlot, identityOf, incompleteNotice,
    });
})();
