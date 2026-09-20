/** The trip page as four pieces of work, sharing one plan and one draft.
 *
 * Everything used to be stacked in the order it was written: the map, the
 * schedule, the visit-execution forms, the export panel and the workbook
 * return, with the plan's own name and dates last. Three customer stops made a
 * 9,317px page at 1024px, and the plan name sat 6,208px down it.
 *
 * Nothing is re-rendered when the zone changes and nothing is unmounted - only
 * which zone is shown. A half-typed briefing is still there when the reader
 * comes back to it, which is the difference between a zone change and a plan
 * change.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const ZONES = ['settings', 'route', 'briefing', 'execution'];
    const DEFAULT_ZONE = 'settings';
    let active = DEFAULT_ZONE;

    function module_() {
        return document.getElementById('module-trip-planner');
    }

    // A map built while its zone was display:none measured itself against a
    // container with no width, and kept that size when the zone opened: tiles
    // on the left, blank to the right, until the window was resized. The map
    // instance is asked to measure again - not rebuilt, so the zoom, the
    // markers and whatever the reader had chosen all stay.
    function remeasureMap(zone) {
        const map = typeof State === 'undefined' ? null : State?.tripMap;
        if (!map?.invalidateSize) return;
        const host = document.getElementById('trip-map');
        if (host?.closest?.('[data-trip-zone]')?.dataset?.tripZone !== zone) return;
        const afterLayout = window.requestAnimationFrame
            || (callback => setTimeout(callback, 0));
        afterLayout(() => map.invalidateSize());
    }

    function show(zone) {
        const chosen = ZONES.includes(zone) ? zone : DEFAULT_ZONE;
        // `State` is a const global in the page and simply absent in the
        // zone harness, where optional chaining cannot save a name that was
        // never declared.
        const planId = typeof State === 'undefined'
            ? null : State?.currentTripPlan?.id || null;
        // Where the reader was in the zone they are leaving, so coming back
        // does not start them at the top of a route they read halfway through.
        if (active && active !== chosen) window.TripRouteFocus?.remember?.(planId, active);
        active = chosen;
        const host = module_();
        if (!host) return chosen;
        host.dataset.activeZone = chosen;
        host.querySelectorAll('[data-trip-zone-tab]').forEach(tab => {
            const selected = tab.dataset.tripZoneTab === chosen;
            tab.classList.toggle('active', selected);
            tab.setAttribute('aria-selected', String(selected));
        });
        remeasureMap(chosen);
        // The candidate panel can only be measured once its zone is showing,
        // and where it starts depends on how tall the pinned bar is.
        window.TripBarOffset?.sync?.();
        window.TripSideHeight?.sync?.();
        // Looking at it is what makes it no longer news.
        window.TripZoneUpdates?.seen?.(chosen);
        // Nothing is saved or discarded by moving between zones; the bar just
        // says the same truth from wherever the reader now is.
        window.TripRouteBar?.render?.();
        window.TripRouteFocus?.restore?.(planId, chosen);
        return chosen;
    }

    function current() {
        return active;
    }

    // The plan being worked on, said above the zones so it is true whichever
    // zone is open.
    function renderHeader(plan) {
        // The bar beside the plan's name says what is true about its route, and
        // it is redrawn from here: every path that changes the plan redraws the
        // plan, and the four zones share this one bar.
        window.TripRouteBar?.render?.();
        // Same reason: this is where every change to the plan arrives, so it is
        // where the zones the reader is not looking at can be compared.
        window.TripZoneUpdates?.sync?.(plan
            || (typeof State === 'undefined' ? null : State?.currentTripPlan));
        // The candidate list says which customers are already on the plan, and
        // it read that once when the candidates loaded. Every stop added since
        // left it offering to add a customer that is already there - until
        // something else happened to redraw it.
        window.renderTripCandidates?.();
        window.TripBarOffset?.sync?.();
        window.TripSideHeight?.sync?.();
        const name = document.getElementById('trip-zone-plan-name');
        const dates = document.getElementById('trip-zone-plan-dates');
        if (!name || !dates) return;
        if (!plan?.id) {
            name.textContent = tr('No plan selected');
            dates.textContent = '';
            return;
        }
        name.textContent = plan.title || tr('Untitled plan');
        const range = [plan.start_date, plan.end_date].filter(Boolean).join(' → ');
        dates.textContent = range || tr('No dates set');
    }

    // A plan the reader has just opened starts where its settings are; one they
    // were already working on stays where they were.
    function planChanged(plan, previousId) {
        renderHeader(plan);
        if (plan?.id === previousId) return;
        // The screen position being left behind belongs to the plan being left.
        // By the time this runs the plan on screen is already the new one, so
        // the id to file it under is the one passed in - remembering it under
        // the new plan starts its first zone halfway down another plan.
        window.TripRouteFocus?.remember?.(previousId, active);
        // Anything still on its way to the old plan's map belongs to that plan,
        // not to this one; and nothing on the new plan is chosen yet.
        window.TripMapFocus?.clear?.();
        window.TripSelection?.clear?.();
        active = null;
        show(DEFAULT_ZONE);
    }

    window.TripZones = Object.freeze({
        show, current, renderHeader, planChanged, ZONES, DEFAULT_ZONE,
    });
})();
