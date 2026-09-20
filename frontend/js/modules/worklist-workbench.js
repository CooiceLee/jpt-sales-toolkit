/** The list-beside-the-panel shell, once, for every worklist that uses it.
 *
 * The follow-up page proved the shape: the list answers "which one?" in a
 * narrow column and the lead's own panel takes the rest of the width, starting
 * at the top of the list rather than the top of the window. Everything in here
 * is that mechanic - which view, how dense, where the panel begins, what is
 * shown when there is nothing to show - and none of it is about follow-ups.
 *
 * What each page keeps for itself is what its rows say. That is business
 * knowledge, and copying a row layout between pages is how a queue ends up
 * showing fields nobody on that page needs.
 */
(function () {
    'use strict';

    // One driver for every workbench. The list scrolls with the page while the
    // panel beside it is fixed, so the panel's top has to be recomputed *while
    // the page scrolls* - a ResizeObserver never fires for a scroll, and the
    // panel stayed at the coordinate the list had on the first screen: a band
    // of empty page opened above it, growing with every pixel scrolled.
    const positioners = new Set();
    let frame = 0;

    function scheduleSync() {
        if (frame) return;
        // Marked before the frame is asked for, not after: a callback that
        // runs while the assignment is still in flight would leave the flag
        // set and every later scroll would be dropped.
        frame = 1;
        requestAnimationFrame(() => {
            frame = 0;
            positioners.forEach(run => run());
        });
    }

    // The scrolling element is the one the layout actually scrolls in. Listened
    // to once here rather than once per queue: six listeners would do the same
    // work six times on every frame of the same scroll.
    function watchScrolling() {
        const main = document.querySelector('.main-content');
        if (!main || main.dataset.wbScrollWatched === 'true') return;
        main.dataset.wbScrollWatched = 'true';
        main.addEventListener('scroll', scheduleSync, { passive: true });
    }

    window.addEventListener('resize', scheduleSync);

    function create(key) {
        const module_ = () => document.getElementById(`module-${key}`);
        const list = () => document.getElementById(`${key}-cards`);
        const table = () => document.getElementById(`${key}-table-body`);
        const state = () => document.getElementById(`${key}-state`);
        const layout = () => document.querySelector(`#module-${key} .wb-layout`);

        // Where the panel begins. Measured rather than guessed: the head, the
        // tabs and the filters wrap differently by width and by language.
        function syncPanelTop() {
            const box = layout();
            const app = document.getElementById('app');
            if (!box || !app || module_()?.classList.contains('active') === false) return;
            // Follow the list, and stop at the top of the area the reader can
            // actually see. Clamping to 0 instead would slide the panel under
            // the application header once the list scrolled far enough.
            const main = document.querySelector('.main-content');
            const floor = Math.round(main?.getBoundingClientRect().top || 0);
            // Level with the pinned line, not below it. Anchored to the line's
            // bottom, the panel left a band of empty page its own width wide -
            // at rest, and pinned there while the list scrolled past. The line
            // spans the list column only, so lining the two up covers nothing.
            const context = module_()?.querySelector('.wb-context');
            const anchor = (context || box).getBoundingClientRect().top;
            const top = Math.max(floor, Math.round(anchor));
            app.style.setProperty('--wb-panel-top', `${top}px`);
        }

        function switchButtons(kind, value) {
            document.querySelectorAll(`#${key}-${kind}-switch [data-${kind}]`)
                .forEach(button => {
                    const chosen = button.dataset[kind] === value;
                    button.classList.toggle('active', chosen);
                    button.setAttribute('aria-pressed', String(chosen));
                });
        }

        function setView(view) {
            const host = module_();
            const chosen = view === 'table' ? 'table' : 'list';
            if (host) host.dataset.view = chosen;
            syncPanelTop();
            switchButtons('view', chosen);
        }

        function setDensity(density) {
            const host = module_();
            const chosen = density === 'compact' ? 'compact' : 'comfortable';
            if (host) host.dataset.density = chosen;
            syncPanelTop();
            switchButtons('density', chosen);
        }

        // Nothing to show, or the request failed: said once, above both views.
        // Written into the list only, it was invisible in the table - which is
        // where the reader would have been when the filter emptied.
        function drawEmpty(emptyCopy) {
            const box = state();
            if (box) {
                box.innerHTML = window.WorklistCards.emptyState(emptyCopy || {});
                box.hidden = false;
            }
            const frame = layout();
            if (frame) frame.hidden = true;
            const rows = list();
            if (rows) rows.innerHTML = '';
            const grid = table();
            if (grid) grid.innerHTML = '';
            syncPanelTop();
        }

        function draw({ items, emptyCopy, listHtml, tableHtml }) {
            const rows = list();
            if (!rows) return;
            // The line above the list belongs to the query, not to the rows.
            // An emptied list is exactly when the reader needs to see which
            // filter emptied it; leaving the previous sentence there puts the
            // last query's count and conditions over this query's empty page.
            window.WorklistContext?.update?.(key, items);
            if (!items.length) return drawEmpty(emptyCopy);
            const box = state();
            if (box) { box.hidden = true; box.innerHTML = ''; }
            const frame = layout();
            if (frame) frame.hidden = false;
            rows.innerHTML = listHtml;
            const grid = table();
            if (grid) grid.innerHTML = tableHtml;
            // One binding for both views, and it is the production one: click
            // and Enter open the lead's own panel through openInquiryPanel.
            window.WorklistCards.bind(rows);
            if (grid) window.WorklistCards.bind(grid);
            syncPanelTop();
        }

        positioners.add(syncPanelTop);
        document.addEventListener('DOMContentLoaded', () => {
            const frame = layout();
            if (frame && window.ResizeObserver) new ResizeObserver(scheduleSync).observe(frame);
            watchScrolling();
            syncPanelTop();
        }, { once: true });

        return Object.freeze({ draw, drawEmpty, setView, setDensity, syncPanelTop });
    }

    // Anything that changes the height above the list has to ask for a
    // re-measure: the panel is positioned from that height.
    window.WorklistWorkbench = Object.freeze({ create, sync: scheduleSync });
})();
