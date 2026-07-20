(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

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

    function followupEmptyCopy(base, planned, plannedMode, activity) {
        const copy = { title: 'No records in this view' };
        if (!base.length) {
            copy.text = 'No active leads match the current search, owner, technical or business-region filters.';
            return copy;
        }
        if (plannedMode !== 'all' && !planned.length) {
            const missing = base.filter(item =>
                !FollowupFilterModel.calendarDay(item.next_followup_date)
            ).length;
            copy.params = { count: base.length, missing };
            copy.text = missing === base.length
                ? 'All {count} matching active leads are missing a next follow-up date. Set one in lead details or use All Active.'
                : 'No matching active lead is due in this planned-date period; {missing} have no next follow-up date.';
            return copy;
        }
        if (activity.mode === 'custom') {
            const status = FollowupFilterModel.customRangeStatus(activity);
            if (!status.valid) {
                copy.text = status.reason === 'reversed'
                    ? 'The custom activity start date must not be after the end date.'
                    : 'Choose at least one custom activity date.';
                return copy;
            }
        }
        copy.text = activity.mode === 'never'
            ? 'Every matching active lead already has a formal follow-up.'
            : 'No active lead matches the selected planned-date and activity-time filters.';
        return copy;
    }

    async function loadFollowup() {
        try {
            const leads = await ApiClient.listLeads({
                ...getSharedLeadFilters(),
                limit: 100000,
            });
            const base = FollowupFilterModel.annotate(leads
                .filter(lead => ['Assigned', 'Following'].includes(lead.sales_stage))
                .map(lead => leadToCardItem(lead, {
                    next_followup_date: lead.next_followup_date,
                    follow_ups_count: lead.follow_ups_count || 0,
                    latest_follow_up_at: lead.latest_follow_up_at,
                    latest_follow_up_summary: lead.latest_follow_up_summary,
                })));
            const plannedMode = State.currentFilters.followup || 'all';
            const activity = FollowupFilterControls.read();
            const planned = FollowupFilterModel.filterPlanned(base, plannedMode);
            let inquiries = FollowupFilterModel.filterActivity(planned, activity);
            if (activity.mode !== 'all') {
                inquiries = FollowupFilterModel.sortOldestActivity(inquiries);
            }
            setText('followup-count', tr('{shown} of {total} active', {
                shown: inquiries.length,
                total: base.length,
            }));
            renderCards(
                'followup-cards',
                inquiries,
                'followup',
                followupEmptyCopy(base, planned, plannedMode, activity)
            );
        } catch (err) {
            console.error('Followup error:', err);
            setText('followup-count', tr('Unable to load'));
            renderCards('followup-cards', [], 'followup', {
                title: 'Unable to load follow-ups',
                text: 'The follow-up list could not be loaded. Please retry.',
            });
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
