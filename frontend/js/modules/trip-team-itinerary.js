/** What one member of the team actually does on this trip, on their own row.
 *
 * The team card said who is going and how far they travel, and the schedule
 * said what happens half-day by half-day with everybody mixed together. Between
 * the two there was no answer to the plainest question - "what is this person
 * doing on this trip" - and the worst case read as a fault: a member on none of
 * the visits had a blank row and an empty map, with nothing saying why.
 *
 * Built from the schedule the calculation produced, never from the stop list:
 * a stop is on the trip, a stop on *this* member's schedule is a stop they go
 * to, and the two are different for every visit they are not named on.
 */
(function () {
    'use strict';

    const h = value => window.escapeHtml(String(value ?? ''));
    const t = (key, params = {}) => window.I18n?.t(key, params) || key;
    const KINDS = ['customer', 'free'];

    function slot(item) {
        return `${item.date || ''}|${item.period === 'PM' ? '1' : '0'}`;
    }

    /** One entry per place, not per half-day: a two-day visit is one visit. */
    function stops(plan, userId) {
        const seen = new Map();
        (plan?.schedule_items || [])
            .filter(item => item.member_id === userId && KINDS.includes(item.item_type))
            .sort((left, right) => slot(left).localeCompare(slot(right))
                || (left.lane_order ?? 0) - (right.lane_order ?? 0))
            .forEach(item => {
                if (!seen.has(item.source_id)) seen.set(item.source_id, item);
            });
        return [...seen.values()];
    }

    /** Which of this member's stops the calculation flagged, and what it said.
     *
     * A risk naming somebody else is not this member's to answer for, even when
     * they are on the same visit. A risk naming no one belongs to the visit, so
     * everybody who goes to it sees it.
     */
    function risksByStop(plan, userId) {
        const found = new Map();
        (plan?.itinerary_summary?.risks || []).forEach(risk => {
            const whose = risk.member_id || risk.user_id || null;
            if (whose && whose !== userId) return;
            const said = window.TripTeamRisks?.describe?.(plan, risk) || '';
            if (!said) return;
            // Not every risk is a trip that cannot be made. "The customer
            // agreed to the afternoon, you asked for the morning" is a thing to
            // confirm, and calling it impossible is how a card comes to report
            // more failures than the bar above it.
            const blocks = Boolean(window.TripRouteState?.blocks?.(risk.kind));
            [risk.stop_id, ...(risk.stop_ids || [])].filter(Boolean).forEach(id => {
                found.set(id, [...(found.get(id) || []), { said, blocks }]);
            });
        });
        return found;
    }

    // The distance and the return day are already on the member's own line
    // above this; repeating them here is the same fact twice in four lines.
    function summary(plan, member, rows) {
        const visits = rows.filter(row => row.item_type === 'customer').length;
        const personal = rows.length - visits;
        const blocked = rows.filter(row =>
            (row.risks || []).some(risk => risk.blocks)).length;
        const confirm = rows.filter(row =>
            (row.risks || []).length && !(row.risks || []).some(r => r.blocks)).length;
        return [
            t('{count} visits', { count: visits }),
            personal ? t('{count} personal stops', { count: personal }) : '',
            // Said in the summary as well as on the line: a long itinerary
            // scrolls, and the flagged stop may not be the one on screen.
            blocked ? t('{count} do not work', { count: blocked }) : '',
            confirm ? t('{count} to confirm', { count: confirm }) : '',
        ].filter(Boolean).join(' · ');
    }

    // Taking somebody off a visit belongs on the line that visit is listed on.
    // A personal stop is not somebody's attendance, so that one opens its own
    // editor rather than pretending the same action fits.
    function action(item, userId) {
        return item.item_type === 'free'
            ? `<button type="button" class="btn btn-text btn-sm trip-team-line-action"
                onclick="TripFreeStopForm.open('${h(item.source_id)}')"
                >${h(t('Edit'))}</button>`
            : `<button type="button" class="btn btn-text btn-sm trip-team-line-action"
                onclick="TripTeamVisitDrop.drop('${h(userId)}', '${h(item.source_id)}')"
                >${h(t('Not going'))}</button>`;
    }

    function line(item, userId) {
        const when = `${item.date || ''} ${t(item.period === 'PM'
            ? 'Afternoon (PM)' : 'Morning (AM)')}`.trim();
        const risks = item.risks || [];
        const blocks = risks.some(risk => risk.blocks);
        const tone = blocks ? 'is-risky' : risks.length ? 'is-checking' : '';
        return `<li class="${tone}">
            <span class="trip-team-when">${h(when)}</span>
            <span data-business>${h(item.title || '')}</span>
            ${item.item_type === 'free'
                ? `<em>${h(t('Personal stop'))}</em>` : ''}
            ${risks.length ? `<span class="trip-team-risk-flag"
                aria-label="${h(t(blocks ? 'Does not work' : 'To confirm'))}"
                >${blocks ? '!' : '?'}</span>
                <span class="trip-team-risk-why">${
                    h(risks.map(risk => risk.said).join(' '))}</span>` : ''}
            ${action(item, userId)}
        </li>`;
    }

    // Nothing on the schedule is a fact about the plan, not a gap in this card:
    // said here, with the one thing that changes it.
    function nothing(plan, member) {
        const totals = plan?.itinerary_summary?.member_totals?.[member.user_id];
        // Out of date is not the same as never calculated. Taking somebody off
        // a visit puts the route out of date, which empties every member's
        // list at once - and "no route calculated yet" would then read as work
        // lost rather than work waiting to be recalculated. Invalidating also
        // clears the generated-at stamp, so the summary is what tells them
        // apart: a route that was invalidated says so.
        const summary = plan?.itinerary_summary || {};
        const stale = summary.stale === true || Boolean(summary.invalidated_at);
        const pending = !plan?.itinerary_generated_at || stale;
        return `<p class="trip-team-itinerary-empty">${h(stale
            ? t('The route is out of date since the last change. Calculate it again to see this trip.')
            : pending
            ? t('No route calculated yet, so there is nothing to show here yet.')
            : totals?.route_complete === false
            ? t('The plan cannot work out where this person is, so their trip is not planned.')
            : t('Not on any visit, so there is no trip to make.'))}</p>
            ${!pending && totals?.route_complete !== false
                ? `<p class="trip-team-itinerary-hint">${h(t(
                    'Add them to a visit under Visit preparation, then calculate the route again.'
                ))}</p>` : ''}`;
    }

    function render(plan, member) {
        if (!member?.user_id) return '';
        const flagged = risksByStop(plan, member.user_id);
        const rows = stops(plan, member.user_id)
            .map(row => ({ ...row, risks: flagged.get(row.source_id) || [] }));
        return `<div class="trip-team-itinerary"
            aria-label="${h(t('Trip for {name}', {
                name: member.display_name || member.user_id }))}">
            ${rows.length
                ? `<p class="trip-team-itinerary-head">${h(summary(plan, member, rows))}</p>
                   <ol class="trip-team-itinerary-list">${
                       rows.map(row => line(row, member.user_id)).join('')}</ol>`
                : nothing(plan, member)}
        </div>`;
    }

    window.TripTeamItinerary = Object.freeze({ render, stops, summary, risksByStop });
})();
