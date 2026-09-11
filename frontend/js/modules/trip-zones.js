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
        return chosen;
    }

    function current() {
        return active;
    }

    // The plan being worked on, said above the zones so it is true whichever
    // zone is open.
    function renderHeader(plan) {
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
        if (plan?.id !== previousId) show(DEFAULT_ZONE);
    }

    window.TripZones = Object.freeze({
        show, current, renderHeader, planChanged, ZONES, DEFAULT_ZONE,
    });
})();
