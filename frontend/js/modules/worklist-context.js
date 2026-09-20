/** The one line that stays on screen while a long list scrolls.
 *
 * The filters are a tall block at the top of the page. Scroll into a list of a
 * thousand rows and they are gone: the panel on the right still says which
 * lead is open, but nothing on the screen says which list it came out of, how
 * many rows answered the filters, or what those filters were. This keeps that
 * sentence - and only that sentence - pinned to the top.
 *
 * It offers two ways back rather than moving anything on its own: the filters
 * themselves, and the row that is currently open. Scrolling somebody's list
 * for them, every time a save refreshes it, is how a reader loses their place.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const h = value => window.escapeHtml(String(value ?? ''));

    const TITLES = {
        handler: 'Inquiry Handler', followup: 'Follow-up Tracker',
        sampling: 'Pre-sales / Sampling', deal: 'Deal Closer',
        fulfillment: 'Order Fulfillment', aftersales: 'After-sales',
    };

    // The custom activity window is two date inputs beside the select, which
    // says only "custom" - a sentence that stops there does not say which days.
    function activityRange(host) {
        const select = host?.querySelector?.('#followup-activity-filter');
        if (select?.value !== 'custom') return '';
        const from = host.querySelector('#followup-activity-from')?.value || '';
        const to = host.querySelector('#followup-activity-to')?.value || '';
        return from || to ? `${from || '…'} → ${to || '…'}` : '';
    }

    // What the reader chose, in their words. Ids would be honest and useless.
    //
    // Read out of this queue's own controls. Every queue has its own owner,
    // tech and region selects, and the inquiry handler's stage select stays in
    // the page while another queue is open: a document-wide lookup found that
    // one and told a follow-up reader their list was filtered to "Quoted".
    function conditions(key) {
        const shared = State?.stageFilters || {};
        const host = document.getElementById(`module-${key}`);
        const label = selector => {
            const select = host?.querySelector?.(selector);
            if (!select || !select.value || select.value === 'all') return '';
            return select.selectedOptions?.[0]?.textContent?.trim() || select.value;
        };
        // The queues whose status is a row of tabs rather than a select. "All"
        // is the absence of a condition, not one.
        const tab = host?.querySelector?.(
            '.filters-bar .filter-primary .filter-tab.active[data-filter]');
        const parts = [
            tab && tab.dataset.filter !== 'all' ? tab.textContent.trim() : '',
            label('#filter-stage'),
            shared.customerId
                ? tr('Customer: {value}', { value: shared.search || tr('one selected') })
                : shared.search ? tr('Search: {value}', { value: shared.search }) : '',
            label(`#stage-owner-${key}`), label(`#stage-tech-${key}`),
            label(`#stage-region-${key}`),
            label('#followup-activity-filter'), activityRange(host),
        ].filter(Boolean);
        return parts.length ? parts.join(' · ') : tr('No filters');
    }

    function ensure(key) {
        const host = document.getElementById(`module-${key}`);
        const layout = host?.querySelector('.wb-layout');
        if (!host || !layout) return null;
        let row = host.querySelector('.wb-context');
        if (!row) {
            row = document.createElement('div');
            row.className = 'wb-context';
            layout.parentNode.insertBefore(row, layout);
        }
        return row;
    }

    // What each queue last drew, so opening a lead can redraw this one line
    // without asking the server for the list again.
    const drawn = new Map();

    function update(key, items = []) {
        drawn.set(key, items);
        const row = ensure(key);
        if (!row) return;
        const open = State?.currentInquiry?.id || '';
        const selectable = open
            && document.querySelector(`#module-${key} [data-inquiry-id="${open}"]`);
        row.innerHTML = `
            <span class="wb-context-where"><strong>${h(tr(TITLES[key] || key))}</strong>
                <em>${h(tr('{count} shown', { count: items.length }))}</em></span>
            <span class="wb-context-filters" data-business>${h(conditions(key))}</span>
            <span class="wb-context-actions">
                <button type="button" class="btn btn-text btn-sm"
                    onclick="WorklistContext.showFilters('${h(key)}')">${h(tr('Filters'))}</button>
                ${selectable ? `<button type="button" class="btn btn-text btn-sm"
                    onclick="WorklistContext.showOpen('${h(key)}')">${h(tr('Find the open lead'))}</button>` : ''}
            </span>`;
        // This line sits above the list, so its height decides where the panel
        // beside the list begins.
        window.WorklistWorkbench?.sync?.();
    }

    window.WorklistContext = Object.freeze({
        update,
        // The open lead changed: the line says which list is on screen and
        // offers the way back to the row, so it has to follow that.
        refresh() {
            const active = document.querySelector('.module.active')?.id?.replace('module-', '');
            if (active && drawn.has(active)) update(active, drawn.get(active));
        },
        showFilters(key) {
            document.querySelector(`#module-${key} .filters-bar`)
                ?.scrollIntoView({ block: 'start', behavior: 'smooth' });
        },
        // Only when the reader asks. A list that jumps back to the selected row
        // on its own takes the scroll position away from whoever was reading.
        showOpen(key) {
            const open = State?.currentInquiry?.id;
            if (!open) return;
            document.querySelector(`#module-${key} [data-inquiry-id="${open}"]`)
                ?.scrollIntoView({ block: 'center', behavior: 'smooth' });
        },
    });
})();
