/** The trip as one line of time: which days, which half-days, what happens.
 *
 * Built only from what the calculation produced (plan.schedule_items), because
 * that is the one place that knows when anything happens. The stop list knows
 * what is on the trip and the leg list knows how far apart things are; neither
 * knows which morning somebody is in Berlin.
 *
 * Two ways of looking, one model: "everything" reads visits, personal stops and
 * the travel between them; "travel only" keeps the same days and the same
 * order and shows the journeys, each still sitting on the half-day it occupies.
 * Neither is a second copy of the data, and switching between them is reading,
 * not editing - it never marks anything dirty and never recalculates a route.
 *
 * Who is travelling is a filter on the same model. With everybody shown, two
 * colleagues in different cities on the same morning are two entries on that
 * morning - parallel, not a sequence - which is why nothing here joins entries
 * across members into one line.
 */
(function () {
    'use strict';

    const MODES = Object.freeze(['full', 'travel']);
    const state = { member: 'all', mode: 'full' };

    const isLeg = item => String(item?.item_type || '').toLowerCase() === 'leg';
    const dayOf = item => item?.date || '';
    const periodOf = item => (String(item?.period || 'AM').toUpperCase() === 'PM' ? 'PM' : 'AM');

    /** The leg this timeline entry belongs to; an airport transfer names its parent. */
    function legKeyOf(item) {
        return String(item?.source_id || '').split('#')[0];
    }

    function keep(item) {
        if (state.member !== 'all' && item.member_id !== state.member) return false;
        return state.mode !== 'travel' || isLeg(item);
    }

    function slots(items, plan) {
        const grouped = new Map();
        items.forEach(item => {
            const key = periodOf(item);
            grouped.set(key, [...(grouped.get(key) || []), item]);
        });
        return ['AM', 'PM']
            .filter(period => grouped.has(period))
            .map(period => ({
                period,
                entries: window.TripTeamTimeline?.groupSlot?.(grouped.get(period), plan)
                    || grouped.get(period),
            }));
    }

    /** Every day the plan touches, in order, with what happens on each. */
    function days(plan) {
        const items = (plan?.schedule_items || []).filter(keep);
        const byDay = new Map();
        items.forEach(item => {
            const day = dayOf(item);
            if (!day) return;
            byDay.set(day, [...(byDay.get(day) || []), item]);
        });
        return [...byDay.keys()].sort().map(date => ({
            date, slots: slots(byDay.get(date), plan),
        }));
    }

    /**
     * Stops the route has not placed on a day.
     *
     * They stay visible and stay editable: hiding them would make the timeline
     * look complete while a customer nobody has scheduled sits in the plan.
     */
    function unscheduled(plan) {
        if (state.mode === 'travel') return [];
        const placed = new Set((plan?.schedule_items || [])
            .filter(item => !isLeg(item) && dayOf(item))
            .map(item => String(item.source_id)));
        return (plan?.stops || []).filter(stop => !placed.has(String(stop.id)));
    }

    function counts(plan) {
        const items = plan?.schedule_items || [];
        const shown = items.filter(keep);
        const legKeys = list => new Set(list.filter(isLeg).map(legKeyOf));
        const stopIds = list => new Set(list.filter(item => !isLeg(item)).map(item => String(item.source_id)));
        return {
            days: days(plan).length,
            stops: stopIds(shown).size, allStops: stopIds(items).size,
            legs: legKeys(shown).size, allLegs: legKeys(items).size,
            unscheduled: unscheduled(plan).length,
        };
    }

    function members(plan) {
        return (plan?.members || []).map(member => ({
            id: member.user_id,
            name: member.display_name || member.user_id,
        }));
    }

    function setMember(value) {
        state.member = value || 'all';
        window.TripTimelineToolbar?.render?.();
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
    }

    function setMode(value) {
        state.mode = MODES.includes(value) ? value : 'full';
        window.TripTimelineToolbar?.render?.();
        window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
    }

    window.TripTimelineModel = Object.freeze({
        MODES, days, unscheduled, counts, members, legKeyOf, isLeg,
        setMember, setMode,
        member: () => state.member,
        mode: () => state.mode,
    });
})();
