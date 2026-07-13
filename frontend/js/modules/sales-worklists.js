(function () {
    'use strict';

    async function loadHandler() {
        const stage = document.getElementById('filter-stage')?.value || 'New';
        try {
            const params = getSharedLeadFilters();
            if (stage) params.sales_stage = stage;
            const leads = await ApiClient.listLeads(params);
            const inquiries = leads.map(lead => ({
                ...leadToCardItem(lead),
                product: lead.product_category,
            }));
            State.inquiries = inquiries;
            setText('inquiry-count', `${inquiries.length} leads`);
            renderCards('handler-cards', inquiries);
        } catch (err) {
            console.error('Handler error:', err);
        }
    }

    function filterFollowupsByDate(inquiries, filter) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (filter === 'overdue') {
            return inquiries.filter(item => item.next_followup_date && new Date(item.next_followup_date) < today);
        }
        if (filter === 'today') {
            return inquiries.filter(item => item.next_followup_date
                && new Date(item.next_followup_date).toDateString() === today.toDateString());
        }
        if (filter === 'week') {
            const weekLater = new Date(today);
            weekLater.setDate(weekLater.getDate() + 7);
            return inquiries.filter(item => {
                const date = item.next_followup_date ? new Date(item.next_followup_date) : null;
                return date && date >= today && date <= weekLater;
            });
        }
        return inquiries;
    }

    async function loadFollowup() {
        try {
            const leads = await ApiClient.listLeads(getSharedLeadFilters());
            let inquiries = leads
                .filter(lead => ['Assigned', 'Following'].includes(lead.sales_stage))
                .map(lead => leadToCardItem(lead, {
                    next_followup_date: lead.next_followup_date,
                    follow_ups_count: lead.follow_ups_count || 0,
                }));
            inquiries = filterFollowupsByDate(inquiries, State.currentFilters.followup || 'all');
            setText('followup-count', `${inquiries.length} active`);
            renderCards('followup-cards', inquiries, 'followup');
        } catch (err) {
            console.error('Followup error:', err);
        }
    }

    async function loadDeal() {
        try {
            const leads = await ApiClient.listLeads(getSharedLeadFilters());
            const dealLeads = leads.filter(lead => ['Quoted', 'Won', 'Lost'].includes(lead.sales_stage));
            let inquiries = dealLeads
                .filter(lead => ['Quoted', 'Lost'].includes(lead.sales_stage))
                .map(lead => leadToCardItem(lead));
            const won = dealLeads.filter(lead => lead.sales_stage === 'Won');
            const wonValue = won.reduce((sum, lead) => sum + (parseFloat(lead.deal_amount) || 0), 0);
            setText('deal-quoting', dealLeads.filter(lead => lead.sales_stage === 'Quoted').length);
            setText('deal-won', won.length);
            setText('deal-value', Math.round(wonValue / 1000).toLocaleString());
            const filter = State.currentFilters.deal || 'all';
            if (filter !== 'all') inquiries = inquiries.filter(item => item.stage === filter);
            renderCards('deal-cards', inquiries, 'deal');
        } catch (err) {
            console.error('Deal error:', err);
        }
    }

    window.loadHandler = loadHandler;
    window.loadFollowup = loadFollowup;
    window.loadDeal = loadDeal;
})();
