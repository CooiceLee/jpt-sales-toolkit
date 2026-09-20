/** How much of the scrolling area the pinned bar covers.
 *
 * The bar holds the plan's identity, its status and the two route actions, so
 * it stays at the top of .main-content while the zones scroll under it. Every
 * other pinned thing in this module then has to start below it - and by how
 * much is not a number that can be typed into the stylesheet: the bar is two
 * rows, its status is a sentence, and both change with the language, the zoom
 * and the width. So it is measured, and published once as a custom property
 * the stylesheet can use for sticky tops and for scroll margins.
 */
(function () {
    'use strict';

    let frame = 0;

    function sync() {
        const bar = document.querySelector('#module-trip-planner .trip-zone-bar');
        const root = document.getElementById('module-trip-planner');
        if (!bar || !root) return;
        // Measured while the module is hidden every edge is zero, and "0px"
        // would then be kept until something else happened to ask again.
        if (!bar.offsetParent) return;
        const height = Math.round(bar.getBoundingClientRect().height);
        if (height > 0) root.style.setProperty('--trip-bar-height', `${height}px`);
    }

    function schedule() {
        if (frame) return;
        frame = 1;
        requestAnimationFrame(() => { frame = 0; sync(); });
    }

    window.addEventListener('resize', schedule);
    window.addEventListener('language:changed', schedule);
    document.addEventListener('DOMContentLoaded', schedule, { once: true });

    window.TripBarOffset = Object.freeze({ sync: schedule });
})();
