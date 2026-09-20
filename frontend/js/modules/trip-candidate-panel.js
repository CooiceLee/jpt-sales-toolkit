/** The customer list, open when somebody is adding customers.
 *
 * It held a quarter of the window at every moment of planning a trip, which is
 * why the timeline and the editor beside it could not both fit on a 1440 screen
 * and the editor ended up under a month of days. Adding customers is a phase,
 * not a permanent state: the list opens on request, keeps every filter, page
 * and action it had, and gives the width back when it is closed.
 */
(function () {
    'use strict';

    const root = () => document.getElementById('module-trip-planner');
    const isOpen = () => root()?.dataset.candidates === 'open';

    function apply() {
        // The pinned list can only be measured once it is on screen.
        window.TripSideHeight?.sync?.();
        window.TripTimelineToolbar?.render?.();
        if (State.tripMap) window.setTimeout(() => State.tripMap.invalidateSize(), 220);
    }

    function open() {
        const module = root();
        if (!module) return;
        module.dataset.candidates = 'open';
        window.renderTripCandidates?.();
        apply();
        document.querySelector('.trip-side[data-trip-zone="route"]')
            ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    function close() {
        const module = root();
        if (!module) return;
        module.dataset.candidates = 'closed';
        apply();
    }

    function toggle() { return isOpen() ? close() : open(); }

    window.TripCandidatePanel = Object.freeze({ open, close, toggle, isOpen });
})();
