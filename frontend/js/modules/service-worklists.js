(function () {
    'use strict';

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
            setText('fulfillment-count', `${inquiries.length} orders`);
            renderCards('fulfillment-cards', inquiries, 'fulfillment');
        } catch (err) {
            console.error('Fulfillment error:', err);
        }
    }

    function deriveServiceStatus(lead, tasks) {
        if (lead.service_status && lead.service_status !== 'None') return lead.service_status;
        const statuses = new Set(tasks.map(task => task.status));
        return ['Open', 'In Progress', 'Resolved', 'Closed'].find(status => statuses.has(status)) || 'None';
    }

    async function loadAftersales() {
        try {
            const [leads, tasks] = await Promise.all([
                ApiClient.listLeads(getSharedLeadFilters()),
                ApiClient.listAfterSalesTasks().catch(() => []),
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
                });
            }).filter(item => item.service_status !== 'None');
            const filter = State.currentFilters.aftersales || 'all';
            if (filter !== 'all') inquiries = inquiries.filter(item => item.service_status === filter);
            setText('aftersales-count', `${inquiries.length} issues`);
            renderCards('aftersales-cards', inquiries, 'aftersales');
        } catch (err) {
            console.error('Aftersales error:', err);
        }
    }

    window.loadFulfillment = loadFulfillment;
    window.loadAftersales = loadAftersales;
})();
