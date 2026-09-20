/** Which of the four zones changed because of something done in another one.
 *
 * The zones share one plan, so work in any of them moves the others: saving a
 * route rewrites the daily schedule and every member's totals, a preparation
 * that changes where a visit happens puts the saved route out of date, and a
 * returned workbook fills in execution results. The reader only ever sees one
 * zone, so all of that happened out of sight and they had no reason to go and
 * look.
 *
 * Each zone gets a fingerprint of the data it shows. When the fingerprint of a
 * zone the reader is *not* looking at changes, that zone is marked; opening it
 * clears the mark. Nothing here decides what changed or why - it compares what
 * the server sent, so a mark always stands for a real difference in that zone.
 */
(function () {
    'use strict';

    const t = (key, params = {}) => window.I18n?.t(key, params) || key;
    const stops = plan => plan?.stops || [];

    // What each zone puts on screen, and nothing else: a route recalculation
    // must not mark the preparation zone, and a saved preparation must not mark
    // the execution zone.
    const SHAPES = Object.freeze({
        settings: plan => JSON.stringify([
            plan.title, plan.start_date, plan.end_date, plan.region,
            plan.origin_name, plan.origin_lat, plan.origin_lng,
            plan.destination_name, plan.destination_lat, plan.destination_lng,
            plan.travel_mode, plan.route_order_mode, plan.transport_mode_priority,
            plan.avoid_weekends, plan.holiday_dates, plan.description,
            (plan.members || []).map(member => [
                member.user_id, member.origin_name_override,
                member.origin_lat_override, member.origin_lng_override,
                member.destination_name_override,
                member.destination_lat_override, member.destination_lng_override,
                member.departure_date,
            ]),
            plan.itinerary_summary?.member_totals,
        ]),
        route: plan => JSON.stringify([
            plan.itinerary_generated_at, plan.itinerary_summary?.stale,
            plan.itinerary_summary?.valid, plan.itinerary_summary?.risks,
            (plan.schedule_items || []).map(item => [
                item.member_id, item.item_type, item.source_id,
                item.date, item.period, item.selected_mode,
            ]),
            stops(plan).map(stop => [
                stop.id, stop.sequence_no, stop.planned_date,
                stop.planned_start_period, stop.planned_end_date,
            ]),
        ]),
        briefing: plan => JSON.stringify(stops(plan).map(stop => [
            stop.id, stop.confirmation_status, stop.visit_purpose,
            stop.briefing, stop.visit_location,
        ])),
        // Every field the execution card writes back - the list the card's own
        // payload uses. Anything left out is a change the reader is not told
        // about: a quote asked for, a sample promised, a budget written down.
        execution: plan => JSON.stringify(stops(plan).map(stop => [
            stop.id, stop.result_status, stop.result_notes, stop.actual_visit_date,
            stop.actual_visit_period, stop.visit_customer_needs,
            stop.visit_competitor, stop.visit_budget, stop.visit_decision_maker,
            stop.visit_next_action, stop.visit_followup_due_date,
            stop.visit_sample_needed, stop.visit_quote_needed,
            (stop.attachments || []).length,
        ])),
    });

    let planId = null;
    let baseline = {};
    const marked = new Set();

    function fingerprints(plan) {
        return Object.fromEntries(Object.entries(SHAPES)
            .map(([zone, shape]) => [zone, shape(plan)]));
    }

    function paint() {
        document.querySelectorAll('[data-trip-zone-tab]').forEach(tab => {
            const zone = tab.dataset.tripZoneTab;
            const changed = marked.has(zone);
            tab.classList.toggle('has-update', changed);
            const dot = tab.querySelector('.trip-zone-dot');
            if (changed && !dot) {
                const mark = document.createElement('i');
                mark.className = 'trip-zone-dot';
                mark.setAttribute('role', 'img');
                mark.setAttribute('aria-label', t('Updated by a change elsewhere'));
                tab.appendChild(mark);
            } else if (!changed && dot) {
                dot.remove();
            }
            if (changed) tab.title = t('Updated by a change elsewhere');
            else tab.removeAttribute('title');
        });
    }

    /** Compare what the server just sent with what the reader has seen. */
    function sync(plan) {
        if (!plan?.id) {
            planId = null; baseline = {}; marked.clear();
            return paint();
        }
        const now = fingerprints(plan);
        // Another plan is not an update to this one: its four zones are all new
        // to the reader, and marking them all would mean nothing.
        if (plan.id !== planId) {
            planId = plan.id; baseline = now; marked.clear();
            return paint();
        }
        const open = window.TripZones?.current?.();
        Object.entries(now).forEach(([zone, value]) => {
            if (value === baseline[zone]) return;
            baseline[zone] = value;
            if (zone !== open) marked.add(zone);
        });
        paint();
    }

    /** The reader is looking at it now, so it is no longer news. */
    function seen(zone) {
        if (!zone || !marked.has(zone)) return;
        marked.delete(zone);
        paint();
    }

    window.TripZoneUpdates = Object.freeze({
        sync, seen, fingerprints, pending: () => [...marked],
    });
})();
