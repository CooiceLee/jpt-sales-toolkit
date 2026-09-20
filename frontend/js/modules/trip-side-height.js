/** How tall the pinned candidate panel may be, measured where it actually is.
 *
 * The panel is sticky and its height was a fixed sum: the window minus the
 * application header. That is only true once it has pinned. Before that it
 * starts further down - below the plan's own header and the zone tabs - and
 * keeps the full height, so its bottom sits below the window. Scrolling the
 * panel then reached its end with rows still off screen, and the only way to
 * see them was to scroll the whole page: the inner scrollbar said "that is
 * everything" when it was not.
 *
 * So the height is whatever is left between where the panel starts and the
 * bottom of the area the reader can see, recomputed while the page scrolls.
 */
(function () {
    'use strict';

    const FLOOR = 280;                     // below this it is not a list any more
    let frame = 0;

    function sync() {
        const side = document.querySelector('.trip-side[data-trip-zone]');
        const main = document.querySelector('.main-content');
        if (!side || !main) return;
        // Stacked in one column there is nothing pinned and nothing to cap.
        if (getComputedStyle(side).position !== 'sticky') {
            side.style.removeProperty('--trip-side-height');
            return;
        }
        const box = side.getBoundingClientRect();
        // Measured while its zone is hidden, every edge is zero and the answer
        // is "as tall as the window" - which is then kept until something else
        // happens to ask again.
        if (!side.offsetParent || box.height === 0) return;
        const top = box.top;
        const bottom = Math.min(main.getBoundingClientRect().bottom,
            window.innerHeight);
        side.style.setProperty('--trip-side-height',
            `${Math.max(FLOOR, Math.floor(bottom - top))}px`);
    }

    function schedule() {
        if (frame) return;
        frame = 1;
        requestAnimationFrame(() => { frame = 0; sync(); });
    }

    function watch() {
        const main = document.querySelector('.main-content');
        if (!main || main.dataset.tripSideWatched === 'true') return;
        main.dataset.tripSideWatched = 'true';
        main.addEventListener('scroll', schedule, { passive: true });
    }

    window.addEventListener('resize', schedule);
    document.addEventListener('DOMContentLoaded', () => { watch(); schedule(); },
        { once: true });

    window.TripSideHeight = Object.freeze({ sync: schedule, watch });
})();
