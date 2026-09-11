/** Step 02: the inquiries waiting to be handled, as a list beside the panel.
 *
 * Split out of the shared worklist module when it grew past what one file
 * should hold. Nothing here decides business rules: the filter comes from the
 * page, the order from WorklistSort, and the rows from the shared renderer.
 */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

    async function loadHandler() {
        // "All stages" is the empty value, and `||` read it as "nothing chosen"
        // and filtered to New: the option was on the page but never worked.
        const select = document.getElementById('filter-stage');
        const stage = select ? select.value : 'New';
        const request = WorklistRequest.begin('handler');
        try {
            const params = getSharedLeadFilters();
            if (stage) params.sales_stage = stage;
            const page = await ApiClient.listAllLeads(params);
            if (!WorklistRequest.isCurrent(request)) return;
            const inquiries = WorklistSort.handler(page.items.map(lead => ({
                ...leadToCardItem(lead),
                product: lead.product_category,
                // Flattened to 0, a lead nobody priced reads as "Deal 0".
                deal_amount: lead.deal_amount ?? null,
                estimated_value: lead.estimated_value ?? null,
            })));
            State.inquiries = inquiries;
            setText('inquiry-count', [
                tr('{count} leads', { count: inquiries.length }),
                PagedFetch.note(page),
            ].filter(Boolean).join(' · '));
            HandlerWorkbench.render(inquiries);
        } catch (err) {
            console.error('Handler error:', err);
            if (!WorklistRequest.isCurrent(request)) return;  // an older query's failure
            setText('inquiry-count', tr('Unable to load'));
            HandlerWorkbench.render([], { title: 'Unable to load',
                text: 'Unable to load inquiries. Please retry.' });
        }
    }

    window.loadHandler = loadHandler;
})();
