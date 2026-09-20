/** The trip drawn as days: one line of time, read top to bottom.
 *
 * A day is the heading, its half-days are the rows, and inside a row are the
 * things that happen: visits, personal stops and the journeys between them.
 * Colleagues doing the same thing at the same time are one entry naming them
 * all; two people in different places on the same morning are two entries on
 * that morning, because that is what parallel means - nothing here joins them
 * into a line that would read as one person's route.
 *
 * Choosing an entry selects it. It does not open another zone, scroll the page
 * or start an edit: the panel beside the line answers "what about it", and the
 * map shows the same choice from above.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);
    const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    function weekdayOf(date) {
        const parsed = new Date(`${date}T00:00:00Z`);
        return Number.isNaN(parsed.getTime()) ? '' : t(WEEKDAYS[parsed.getUTCDay()]);
    }

    function dayCount(day) {
        const entries = day.slots.flatMap(slot => slot.entries);
        const legs = entries.filter(entry => window.TripTimelineModel?.isLeg?.(entry)).length;
        return [
            entries.length - legs ? t('{count} stops', { count: entries.length - legs }) : '',
            legs ? t('{count} legs', { count: legs }) : '',
        ].filter(Boolean).join(' · ');
    }

    function renderDay(day, plan) {
        const slots = day.slots.map(slot => window.TripTeamTimelineView.renderSlot(
            `${day.date}|${slot.period}`,
            slot.entries.map(entry => ({
                ...entry, commitment: window.TripTeamTimelineView.commitment(plan, entry),
            }))
        )).join('');
        return `<section class="trip-day" data-day="${h(day.date)}">
            <header class="trip-day-head">
                <h3>${h(day.date)}</h3>
                <span class="trip-day-weekday">${h(weekdayOf(day.date))}</span>
                <span class="trip-day-count">${h(dayCount(day))}</span>
            </header>
            <div class="trip-day-body">${slots}</div>
        </section>`;
    }

    /** Stops the route has not placed: still on the plan, still editable. */
    function renderUnplaced(stops) {
        if (!stops.length) return '';
        return `<section class="trip-day is-unplaced">
            <header class="trip-day-head"><h3>${h(t('Not scheduled'))}</h3>
                <span class="trip-day-count">${h(t('{count} stops', { count: stops.length }))}</span>
            </header>
            <div class="trip-day-body"><div class="trip-team-slot-body">
                ${stops.map(stop => `<button type="button" class="trip-team-entry is-customer${
                    window.TripSelection?.is?.('stop', stop.id) ? ' is-selected' : ''}"
                    data-kind="stop" data-id="${h(stop.id)}"
                    onclick="TripSelection.select('stop', '${h(stop.id)}')">
                    <span class="trip-team-entry-who">${h(t(
                        stop.stop_kind === 'free' ? 'Personal stop' : 'Customer visit'))}</span>
                    <strong data-business>${h(stop.customer_name || stop.location_name || t('Untitled'))}</strong>
                    <em>${h(t('No date yet'))}</em>
                </button>`).join('')}
            </div></div>
        </section>`;
    }

    function render(plan, target = document.getElementById('trip-schedule-list')) {
        if (!target) return;
        const model = window.TripTimelineModel;
        const days = model?.days?.(plan) || [];
        const unplaced = model?.unscheduled?.(plan) || [];
        if (!days.length && !unplaced.length) {
            target.innerHTML = `<div class="empty-state compact">${h(t(
                'Save or preview a route to create the team timeline.'))}</div>`;
            return;
        }
        target.innerHTML = (window.TripTeamTimeline?.incompleteNotice?.(plan) || '')
            + days.map(day => renderDay(day, plan)).join('')
            + renderUnplaced(unplaced);
    }

    /**
     * Move the highlight without redrawing the line.
     *
     * Redrawing loses the reader's scroll position in a thirty-day plan, and
     * choosing something is not a change to what the days contain.
     */
    function mark() {
        const selection = window.TripSelection?.get?.();
        document.querySelectorAll('#trip-schedule-list .trip-team-entry[data-id]')
            .forEach(entry => {
                // The same rule the entry was drawn with - a journey is the
                // connection and whose journey it is - so the highlight cannot
                // land on a row the panel is not editing.
                const members = (entry.dataset.members || '').split(',').filter(Boolean);
                const selected = !!selection && entry.dataset.kind === selection.kind
                    && window.TripSelection.is(entry.dataset.kind, entry.dataset.id, members);
                entry.classList.toggle('is-selected', selected);
                entry.setAttribute('aria-pressed', String(selected));
            });
    }

    /** Bring one day into view without changing what is selected. */
    function goToDay(date) {
        const day = document.querySelector(`#trip-schedule-list .trip-day[data-day="${date}"]`);
        day?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    window.TripTimelineView = Object.freeze({ render, mark, goToDay, weekdayOf });
})();
