/** The one thing chosen on the timeline, and everything there is to do to it.
 *
 * Every stop and every journey used to carry its own open form, stacked in two
 * long columns below the days. What a reader does with a trip is one thing at a
 * time - this visit, that flight - so one form is open: the one belonging to
 * what they chose. The forms themselves are unchanged; this decides which of
 * them is on screen and says what the object is before the fields start.
 *
 * Nothing is auto-selected. Arriving at the plan and being scrolled into
 * somebody's visit form is not reading, and the guidance line costs less than
 * a wrong guess.
 */
(function () {
    'use strict';

    const h = value => escapeHtml(value ?? '');
    const t = (key, params = {}) => I18n.t(key, params);

    function context(lines) {
        const shown = lines.filter(Boolean);
        return shown.length
            ? `<dl class="trip-detail-facts">${shown.map(([term, value]) =>
                `<div><dt>${h(term)}</dt><dd>${value}</dd></div>`).join('')}</dl>` : '';
    }

    // Three different times, never one - see trip-stop-times.js.
    const scheduled = stop => window.TripStopTimes?.scheduled?.(stop) || '-';
    const agreed = stop => window.TripStopTimes?.agreed?.(stop) || '-';
    const visited = stop => window.TripStopTimes?.visited?.(stop) || '-';

    /**
     * The task the reader came here for, named and in front of the fields.
     *
     * Landing in a form headed "selected item" leaves somebody who clicked
     * "set agreed visit time" to work out which of nine fields they wanted.
     * The fields themselves are the same ones - the block below is the card's
     * own agreed-time area, emphasised, not a second copy with the same ids.
     */
    function agreeTask(stop) {
        const identity = [stop.lead_display_id].filter(Boolean).join(' · ');
        return `<section class="trip-agree-task">
            <h3>${h(t('Setting the agreed visit time'))}</h3>
            <p class="trip-agree-who" data-business>${h(stop.customer_name || t('Untitled'))}${
                identity ? ` · ${h(identity)}` : ''}</p>
            <p class="trip-agree-reference">${h(t('Planned slot'))}: ${h(scheduled(stop))} · ${
                h(t('for reference only'))}</p>
        </section>`;
    }

    function stopDetail(plan, stop) {
        const index = (plan.stops || []).findIndex(item => item.id === stop.id);
        // Who is going, said the way the rest of the trip says it.
        const people = window.TripVisitState?.internalParticipantsLine?.(stop) || '';
        const agreeing = window.TripSelection?.get?.()?.intent === 'agree'
            && stop.stop_kind !== 'free';
        return `<div class="trip-detail-head">
                <span class="trip-detail-kind">${h(t(
                    stop.stop_kind === 'free' ? 'Personal stop' : 'Customer visit'))}</span>
                <h3 data-business>${h(stop.customer_name || stop.location_name || t('Untitled'))}</h3>
            </div>
            ${agreeing ? agreeTask(stop) : ''}
            ${context([
                [t('Planned slot'), h(scheduled(stop))],
                [t('Agreed with customer'), h(agreed(stop))],
                [t('Actually visited'), h(visited(stop))],
                [t('Where'), `<span data-business>${h([stop.city, stop.country].filter(Boolean).join(' · ') || '-')}</span>`],
                stop.stop_kind === 'free' ? null
                    : [t('Lead'), `<span data-business>${h(stop.lead_display_id || '-')}</span>`],
                people ? [t('Who'), `<span data-business>${h(people)}</span>`] : null,
            ])}
            ${(window.renderTripStopCard?.(stop, index, (plan.stops || []).length) || '')
                .replace('class="trip-stop ', agreeing ? 'class="trip-stop is-agree-task ' : 'class="trip-stop ')}
            <div class="trip-detail-links">
                <button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripMapFocus.show('stop', '${h(stop.id)}')">${h(t('Show on the map'))}</button>
                ${stop.stop_kind === 'free' ? '' : `<button type="button" class="btn btn-secondary btn-sm"
                    onclick="TripRouteFocus.goToVisit('${h(stop.id)}')">${h(t('Open visit preparation'))}</button>`}
            </div>`;
    }

    /** Which stops this journey runs between, so it is read in its place. */
    function around(plan, leg) {
        const nameOf = stopId => {
            const stop = (plan.stops || []).find(item => String(item.id) === String(stopId));
            return stop ? (stop.customer_name || stop.location_name || '') : '';
        };
        return [nameOf(leg.from_stop_id) || leg.from_label || t('Origin'),
            nameOf(leg.to_stop_id) || leg.to_label || t('Destination')];
    }

    function legDetail(plan, selection) {
        const draft = window.TripPlanningDraft?.get?.();
        const index = window.TripLegRows?.indexOf?.(plan, draft, selection.id,
            selection.members?.length ? selection.members : selection.memberId);
        const rows = window.TripTransportView?.rows?.() || [];
        const row = rows[index];
        if (!row) return empty(t('This journey is no longer part of the route.'));
        const [from, to] = around(plan, row.leg);
        return `<div class="trip-detail-head">
                <span class="trip-detail-kind">${h(t('Travel leg'))}</span>
                <h3 data-business>${h(from)} → ${h(to)}</h3>
            </div>
            ${context([
                [t('When'), h(window.TripLegCard?.schedule?.(row.leg) || '-')],
                [t('Who'), `<span data-business>${h(row.members.join(' · ') || t('Everyone'))}</span>`],
                [t('Distance'), h(window.TripLegCard?.metrics?.(row.leg) || '-')],
            ])}
            ${window.TripLegCard?.render?.(row, index, draft) || ''}`;
    }

    function empty(message) {
        return `<div class="empty-state compact trip-detail-empty">${h(message)}</div>`;
    }

    const back = `<button type="button" class="trip-detail-back"
        onclick="TripSelection.clear(); document.getElementById('trip-schedule-list')?.scrollIntoView({ block: 'start' })">${
        h(t('Back to the timeline'))}</button>`;

    function render(plan) {
        if (!plan?.id) return empty(t('Create or select a plan'));
        const selection = window.TripSelection?.reconcile?.(plan);
        if (!selection) {
            return empty(t('Choose a visit or a journey on the left to see and change it here.'));
        }
        if (selection.kind === 'stop') {
            const stop = (plan.stops || []).find(item => String(item.id) === selection.id);
            return stop ? back + stopDetail(plan, stop) : empty(t('This stop is no longer part of the plan.'));
        }
        return back + legDetail(plan, selection);
    }

    window.TripDetailPanel = Object.freeze({ render });
})();
