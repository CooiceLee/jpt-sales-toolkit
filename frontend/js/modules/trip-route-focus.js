/** Where the page should be looking after a zone change, and what to focus.
 *
 * Switching zones only changed which section was displayed. The scroll position
 * belonged to the window, so leaving a long route at the bottom and opening the
 * short settings zone left the reader somewhere below the end of it, and coming
 * back put them at the top of a route they had scrolled halfway through.
 *
 * So each zone of each plan remembers where its reader was, the first visit
 * starts at the beginning, and another plan starts fresh rather than inheriting
 * the last one's depth. Nothing is redrawn to do it: no form is rebuilt and the
 * map is left alone.
 */
(function () {
    'use strict';

    const remembered = new Map();          // `${planId}:${zone}` -> scrollTop
    const scroller = () => document.querySelector('.main-content');
    const key = (planId, zone) => `${planId || 'none'}:${zone}`;

    // The preparation editor is only ever reached through the one path that
    // also reveals it - taking `hidden` off it from here would show nobody
    // anything - so this asks that module for the element instead of the id.
    const EDITORS = {
        briefing: {
            find: () => window.TripBriefingReveal?.show?.() || null,
            field: 'textarea, input.form-input',
        },
        'free-stop': {
            find: () => document.getElementById('trip-free-stop-editor'),
            field: 'input.form-input, select',
        },
        // Execution is a card per stop, not one editor. The date cannot be
        // changed while a card is unsaved, so the card being typed into is on
        // screen; without its id there is nothing here to go to.
        visit: {
            find: stopId => (stopId
                ? document.getElementById(`visit-card-${stopId}`) : null),
            field: 'textarea, input.form-input, select',
        },
        // The purpose lives on the route card of one visit, which is only on
        // screen while that visit is the one chosen - so going to it chooses it.
        'stop-purpose': {
            find: stopId => {
                if (!stopId) return null;
                if (!document.getElementById(`stop-purpose-${stopId}`)) {
                    window.TripSelection?.select?.('stop', stopId);
                }
                return document.getElementById(`stop-purpose-${stopId}`)?.closest('.trip-stop') || null;
            },
            field: 'input.form-input',
        },
        // One member's places, open on their row of the team card.
        'member-places': {
            find: userId => (userId
                ? document.getElementById(`trip-team-endpoints-${userId}`) : null),
            field: 'select, input.form-input',
        },
    };

    function remember(planId, zone) {
        const main = scroller();
        if (!main || !zone) return;
        remembered.set(key(planId, zone), Math.round(main.scrollTop));
    }

    function restore(planId, zone) {
        const main = scroller();
        if (!main || !zone) return;
        const saved = remembered.get(key(planId, zone));
        if (saved === undefined) {
            // First time in this zone: start where it starts, not wherever the
            // previous zone happened to leave the page. The bar is pinned to
            // the top of the scrollport now, so measuring against the bar
            // would always answer "already there"; the zone's own first panel
            // is what has to come into view, just below the bar.
            const first = document.querySelector(
                `#module-trip-planner [data-trip-zone="${zone}"]`);
            const bar = document.querySelector('#module-trip-planner .trip-zone-bar');
            const cover = bar ? Math.round(bar.getBoundingClientRect().height) : 0;
            main.scrollTop = first
                ? Math.max(0, main.scrollTop + Math.round(first.getBoundingClientRect().top)
                    - Math.round(main.getBoundingClientRect().top) - cover - 8)
                : 0;
            return;
        }
        main.scrollTop = saved;
    }

    // Another plan is not the same reading position. Keeping the old depth put
    // a reader of a two-stop plan below its end.
    function forget(planId) {
        [...remembered.keys()]
            .filter(entry => !planId || !entry.startsWith(`${planId}:`))
            .forEach(entry => remembered.delete(entry));
    }

    function focusEditor(kind, stopId = null) {
        const target = EDITORS[kind];
        const container = target?.find?.(stopId);
        if (!container) return false;
        // Aligned to its own top, not centred: a tall editor centred puts its
        // title - and the reason the reader was sent here - behind the pinned
        // bar. scroll-margin-top keeps that top clear of the bar.
        if (kind !== 'briefing') container.scrollIntoView({ block: 'start', behavior: 'smooth' });
        const field = container.querySelector(target.field);
        // Focus goes to something the reader can type in, not to the container:
        // a scrolled-to box with no caret in it reads as "nothing happened".
        if (field && !field.disabled) field.focus({ preventScroll: true });
        return true;
    }

    /**
     * Recording what happened on a visit, where the fields for it are.
     *
     * The route card plans a visit; the execution card records it, and it is
     * the one with the actual date and half-day the server requires before a
     * visit may be marked as made. Choosing "Visited" on the planning card
     * could only ever be refused.
     */
    function goToVisitRecord(stopId) {
        window.TripZones?.show?.('execution');
        window.setTimeout(() => focusEditor('visit', stopId), 260);
    }

    // "Edit this visit" from the schedule: the target decides the zone, and the
    // zone has to be showing before anything can be scrolled to.
    function goToVisit(stopId) {
        // The same door every other "edit this visit" button uses: it loads the
        // visit, opens its zone and reveals the editor, with the draft guards
        // that belong to it.
        window.TripBriefingActions?.open?.(stopId);
        setTimeout(() => focusEditor('briefing'), 300);
    }

    window.TripRouteFocus = Object.freeze({
        remember, restore, forget, focusEditor, goToVisit, goToVisitRecord,
    });
})();
