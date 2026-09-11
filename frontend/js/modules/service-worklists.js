(function () {
    'use strict';
    const tr = (text, params) => window.I18n?.t(text, params) || text;

    async function loadFulfillment() {
        const request = WorklistRequest.begin('fulfillment');
        try {
            const page = await ApiClient.listAllLeads(getSharedLeadFilters());
            if (!WorklistRequest.isCurrent(request)) return;
            const leads = page.items;
            let inquiries = leads
                .filter(lead => lead.sales_stage === 'Won')
                .map(lead => leadToCardItem(lead, {
                    fulfillment_status: lead.fulfillment_status || 'Not Started',
                    deal_amount: lead.deal_amount ?? null,
                    estimated_value: lead.estimated_value ?? null,
                }));
            const filter = State.currentFilters.fulfillment || 'all';
            if (filter !== 'all') {
                inquiries = inquiries.filter(item => item.fulfillment_status === filter);
            }
            inquiries = WorklistSort.fulfillment(inquiries);
            setText('fulfillment-count', [
                tr('{count} orders', { count: inquiries.length }),
                PagedFetch.note(page),
            ].filter(Boolean).join(' · '));
            FulfillmentWorkbench.render(inquiries);
        } catch (err) {
            console.error('Fulfillment error:', err);
            if (!WorklistRequest.isCurrent(request)) return;
            setText('fulfillment-count', tr('Unable to load'));
            FulfillmentWorkbench.render([], { title: 'Unable to load',
                text: 'Unable to load orders. Please retry.' });
        }
    }

    function deriveTaskServiceStatus(tasks) {
        const statuses = new Set(tasks.map(task => task.status));
        return ['Open', 'In Progress', 'Resolved', 'Closed'].find(status => statuses.has(status)) || 'None';
    }

    function deriveServiceStatus(lead, tasks) {
        // Tech sees only tasks assigned to the signed-in account.  The Lead-level
        // status is global and may have been derived from another Tech's task.
        if (RoleCapabilities.isTech()) return deriveTaskServiceStatus(tasks);
        if (lead.service_status && lead.service_status !== 'None') return lead.service_status;
        return deriveTaskServiceStatus(tasks);
    }

    async function loadAftersales() {
        const request = WorklistRequest.begin('aftersales');
        try {
            // Every page of both lists: one page of tasks used to decide the
            // whole picture, so 105 tasks across five customers came back as
            // one customer and the navigation count disagreed with the cards.
            const [leadPage, taskPage] = await Promise.all([
                ApiClient.listAllLeads(getSharedLeadFilters()),
                ApiClient.listAllAfterSalesTasks(),
            ]);
            if (!WorklistRequest.isCurrent(request)) return;
            const leads = leadPage.items;
            const tasks = taskPage.items;
            const allowedLeadIds = new Set(leads.map(lead => lead.id));
            const tasksByLead = new Map();
            tasks.forEach(task => {
                if (!allowedLeadIds.has(task.lead_id)) return;
                if (!tasksByLead.has(task.lead_id)) tasksByLead.set(task.lead_id, []);
                tasksByLead.get(task.lead_id).push(task);
            });
            let inquiries = leads.map(lead => {
                const leadTasks = tasksByLead.get(lead.id) || [];
                return leadToCardItem(lead, {
                    service_status: deriveServiceStatus(lead, leadTasks),
                    after_sales_count: leadTasks.length,
                    po_number: lead.po_number || '',
                    _afterSalesTasks: leadTasks,
                });
            }).filter(item => item.service_status !== 'None');
            const filter = State.currentFilters.aftersales || 'all';
            if (filter !== 'all') inquiries = inquiries.filter(item => item.service_status === filter);
            inquiries = WorklistSort.aftersales(inquiries);
            setText('aftersales-count', [
                tr('{count} customers', { count: inquiries.length }),
                PagedFetch.note(leadPage, taskPage),
            ].filter(Boolean).join(' · '));
            AftersalesWorkbench.render(inquiries);
        } catch (err) {
            console.error('Aftersales error:', err);
            if (!WorklistRequest.isCurrent(request)) return;
            setText('aftersales-count', tr('Unable to load'));
            AftersalesWorkbench.render([], { title: 'Unable to load',
                text: 'Unable to load after-sales issues. Please retry.' });
        }
    }

    window.loadFulfillment = loadFulfillment;
    window.loadAftersales = loadAftersales;
})();
