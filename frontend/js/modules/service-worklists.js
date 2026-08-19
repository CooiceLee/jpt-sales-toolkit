(function () {
    'use strict';
    const tr = text => window.I18n?.t(text) || text;

    async function loadFulfillment() {
        try {
            const leads = await ApiClient.listLeads(getSharedLeadFilters());
            let inquiries = leads
                .filter(lead => lead.sales_stage === 'Won')
                .map(lead => leadToCardItem(lead, {
                    fulfillment_status: lead.fulfillment_status || 'Not Started',
                }));
            const filter = State.currentFilters.fulfillment || 'all';
            if (filter !== 'all') {
                inquiries = inquiries.filter(item => item.fulfillment_status === filter);
            }
            inquiries = WorklistSort.fulfillment(inquiries);
            setText('fulfillment-count', `${inquiries.length} orders`);
            renderCards('fulfillment-cards', inquiries, 'fulfillment');
        } catch (err) {
            console.error('Fulfillment error:', err);
            setText('fulfillment-count', tr('Unable to load'));
            setPanelError('fulfillment-cards', tr('Unable to load orders. Please retry.'));
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
        try {
            const [leads, tasks] = await Promise.all([
                ApiClient.listLeads(getSharedLeadFilters()),
                ApiClient.listAfterSalesTasks(),
            ]);
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
            setText('aftersales-count', `${inquiries.length} issues`);
            renderCards('aftersales-cards', inquiries, 'aftersales');
        } catch (err) {
            console.error('Aftersales error:', err);
            setText('aftersales-count', tr('Unable to load'));
            setPanelError('aftersales-cards', tr('Unable to load after-sales issues. Please retry.'));
        }
    }

    window.loadFulfillment = loadFulfillment;
    window.loadAftersales = loadAftersales;
})();
