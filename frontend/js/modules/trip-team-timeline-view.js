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
        // Choosing a line shows it on the map. A visit also opens its
        // preparation, which is the thing there is to do with a visit.
        const action = stopId
            ? `TripTeamMap.focusStop('${h(stopId)}');`
                + `TripBriefingActions.open('${h(stopId)}')`
            : (entry.source_id ? `TripTeamMap.focusLeg('${
                h(String(entry.source_id).split('#')[0])}','${
                h(entry.selected_mode || '')}','${
                h((entry.memberIds || [])[0] || '')}')` : '');
        return `<button type="button"
            class="trip-team-entry is-${h(isLeg ? 'leg' : entry.item_type)}${
                entry.unresolved ? ' is-unresolved' : ''}"
            ${action ? `onclick="${action}"` : 'disabled'}>
            <span class="trip-team-entry-who">${h(who)}</span>
            <strong>${h(entry.title || entry.source_id)}${
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
        const [date, period] = slot.split('|');
        return `<section class="trip-team-slot">
            <h4>${h(date)} · ${h(t(period === 'PM' ? 'Afternoon (PM)' : 'Morning (AM)'))}</h4>
            <div class="trip-team-slot-body">${entries.map(renderEntry).join('')}</div>
        </section>`;
    }

    window.TripTeamTimelineView = Object.freeze({
        commitment, renderEntry, renderSlot,
    });
})();
