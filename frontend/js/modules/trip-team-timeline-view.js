/** How one line of the team timeline is drawn. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const modeLabel = value =>
        window.TripScheduleView?.transportModeLabel?.(value) || value || '';

    /**
     * Whether this time is agreed with the customer, decided by us, or neither.
     *
     * A locked visit is confirmed. An unlocked one whose time somebody accepted
     * is our plan. A time only this calculation produced is left unlabelled:
     * calling it planned would claim a decision nobody made, and the next run
     * is free to move it.
     */
    function commitment(plan, entry) {
        if (entry.item_type === 'leg') return '';
        const stop = (plan?.stops || []).find(item => item.id === entry.source_id);
        if (!stop) return '';
        if (stop.schedule_locked) return t('Confirmed');
        return stop.planned_time_accepted ? t('Planned') : '';
    }

    function renderEntry(entry) {
        const isLeg = entry.item_type === 'leg';
        const stopId = !isLeg ? entry.source_id : '';
        const who = entry.members.length
            ? entry.members.join(' · ') : t('Unassigned');
        // Choosing a line selects that object: the panel beside the timeline
        // answers "what about it" and the map shows the same choice from
        // above. It used to open the preparation editor in another zone, which
        // moved the reader off the day they were reading.
        const kind = isLeg ? 'leg' : 'stop';
        const id = isLeg ? String(entry.source_id || '').split('#')[0] : stopId;
        // Whose journey this is travels with the choice: the same connection on
        // two different days is two journeys, and only one of them is the one
        // the panel beside the timeline is editing.
        const members = isLeg ? [...new Set(entry.memberIds || [])].map(String).sort() : [];
        const carried = members.map(value => `'${h(value)}'`).join(', ');
        const action = id
            ? `TripSelection.select('${kind}', '${h(id)}', { mode: '${
                h(entry.selected_mode || '')}', memberId: '${
                h(members[0] || '')}', members: [${carried}] })` : '';
        const selected = !!id && window.TripSelection?.is?.(kind, id, members);
        return `<button type="button"
            class="trip-team-entry is-${h(isLeg ? 'leg' : entry.item_type)}${
                entry.unresolved ? ' is-unresolved' : ''}${selected ? ' is-selected' : ''}"
            data-kind="${h(kind)}" data-id="${h(id)}" data-members="${h(members.join(','))}"
            aria-pressed="${!!selected}"
            ${action ? `onclick="${action}"` : 'disabled'}>
            <span class="trip-team-entry-who">${h(who)}</span>
            <strong data-business>${h(entry.title || entry.source_id)}${
                isLeg && entry.selected_mode
                    ? ` · ${modeLabel(entry.selected_mode)}` : ''}${
                entry.half_day_count > 1
                    ? ` · ${t('Half-day {index} of {count}', {
                        index: entry.half_day_index, count: entry.half_day_count,
                    })}` : ''}</strong>
            ${entry.commitment
                ? `<span class="trip-team-state">${h(entry.commitment)}</span>` : ''}
            ${entry.unresolved
                ? `<em>${h(t('Travel to this visit is not worked out'))}</em>` : ''}
        </button>`;
    }
    function renderSlot(slot, entries) {
        const period = String(slot).split('|')[1];
        return `<section class="trip-team-slot" data-period="${h(period || 'AM')}">
            <h4>${h(t(period === 'PM' ? 'Afternoon (PM)' : 'Morning (AM)'))}</h4>
            <div class="trip-team-slot-body">${entries.map(renderEntry).join('')}</div>
        </section>`;
    }

    window.TripTeamTimelineView = Object.freeze({
        commitment, renderEntry, renderSlot,
    });
})();
