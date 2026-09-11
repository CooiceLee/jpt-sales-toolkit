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
            const top = Math.max(0, Math.round(box.getBoundingClientRect().top));
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

        window.addEventListener('resize', syncPanelTop);
        document.addEventListener('DOMContentLoaded', () => {
            const frame = layout();
            if (frame && window.ResizeObserver) new ResizeObserver(syncPanelTop).observe(frame);
            syncPanelTop();
        }, { once: true });

        return Object.freeze({ draw, drawEmpty, setView, setDensity, syncPanelTop });
    }

    window.WorklistWorkbench = Object.freeze({ create });
})();
