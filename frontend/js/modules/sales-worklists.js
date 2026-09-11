(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

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
        const request = WorklistRequest.begin('followup');
        try {
            const page = await ApiClient.listAllLeads(getSharedLeadFilters());
            if (!WorklistRequest.isCurrent(request)) return;
            const base = FollowupFilterModel.annotate(page.items
                .filter(lead => ['Assigned', 'Following'].includes(lead.sales_stage))
                .map(lead => leadToCardItem(lead, {
                    next_followup_date: lead.next_followup_date,
                    follow_ups_count: lead.follow_ups_count || 0,
                    latest_follow_up_at: lead.latest_follow_up_at,
                    latest_follow_up_summary: lead.latest_follow_up_summary,
                    // Both amounts as the lead carries them: flattened to 0,
                    // a missing deal printed "SEK 0" over a 210,000 estimate.
                    deal_amount: lead.deal_amount ?? null,
                    estimated_value: lead.estimated_value ?? null,
                })));
            const plannedMode = State.currentFilters.followup || 'all';
            const activity = FollowupFilterControls.read();
            const planned = FollowupFilterModel.filterPlanned(base, plannedMode);
            let inquiries = FollowupFilterModel.filterActivity(planned, activity);
            inquiries = WorklistSort.followup(inquiries, { activityMode: activity.mode });
            setText('followup-count', [tr('{shown} of {total} active', {
                shown: inquiries.length,
                total: base.length,
            }), PagedFetch.note(page)].filter(Boolean).join(' · '));
            // Rows beside the panel, not a grid of cards. Same items and
            // filters; grouped by due date only when the sort is by due date.
            FollowupWorkbench.render(
                inquiries,
                followupEmptyCopy(base, planned, plannedMode, activity),
                { groupByDueDate: activity.mode === 'all' }
            );
        } catch (err) {
            console.error('Followup error:', err);
            if (!WorklistRequest.isCurrent(request)) return;
            setText('followup-count', tr('Unable to load'));
            FollowupWorkbench.render([], {
                title: 'Unable to load follow-ups',
                text: 'The follow-up list could not be loaded. Please retry.',
            });
        }
    }

    async function loadDeal() {
        const request = WorklistRequest.begin('deal');
        try {
            const page = await ApiClient.listAllLeads(getSharedLeadFilters());
            if (!WorklistRequest.isCurrent(request)) return;
            const leads = page.items;
            const dealLeads = leads.filter(lead => ['Quoted', 'Won', 'Lost'].includes(lead.sales_stage));
            let inquiries = dealLeads
                .filter(lead => ['Quoted', 'Lost'].includes(lead.sales_stage))
                // Flattened to 0, a deal nobody priced reads as agreed at zero.
                .map(lead => ({ ...leadToCardItem(lead),
                    deal_amount: lead.deal_amount ?? null,
                    estimated_value: lead.estimated_value ?? null }));
            const won = dealLeads.filter(lead => lead.sales_stage === 'Won');
            // Per currency: deals of 10,000 EUR and 10,000 USD are not 20,000
            // of anything, and this figure used to be printed in dollars.
            const wonByCurrency = {};
            let wonWithoutAmount = 0;
            won.forEach(lead => {
                const amount = parseFloat(lead.deal_amount);
                if (!Number.isFinite(amount)) { wonWithoutAmount += 1; return; }
                const code = String(lead.currency || '').trim().toUpperCase() || 'UNSPECIFIED';
                wonByCurrency[code] = (wonByCurrency[code] || 0) + amount;
            });
            setText('deal-quoting', dealLeads.filter(lead => lead.sales_stage === 'Quoted').length);
            setText('deal-won', won.length);
            setText('deal-value', MoneyTotals.text(wonByCurrency));
            // Every figure on this card is computed from the list that was
            // read, so a list that stopped short makes all of them partial.
            setText('deal-value-note', [MoneyTotals.missingNote(wonWithoutAmount),
                PagedFetch.note(page)].filter(Boolean).join(' · '));
            const cycle = DealCycle.measure(dealLeads);
            setText('deal-cycle', DealCycle.text(cycle));
            setText('deal-cycle-note', DealCycle.note(cycle));
            const filter = State.currentFilters.deal || 'all';
            if (filter !== 'all') inquiries = inquiries.filter(item => item.stage === filter);
            inquiries = WorklistSort.deal(inquiries);
            setText('deal-count', [
                tr('{count} leads', { count: inquiries.length }),
                PagedFetch.note(page),
            ].filter(Boolean).join(' · '));
            DealWorkbench.render(inquiries);
        } catch (err) {
            console.error('Deal error:', err);
            if (!WorklistRequest.isCurrent(request)) return;
            ['deal-quoting', 'deal-won', 'deal-value', 'deal-cycle', 'deal-count']
                .forEach(id => setText(id, '—'));
            ['deal-value-note', 'deal-cycle-note'].forEach(id => setText(id, ''));
            DealWorkbench.render([], { title: 'Unable to load',
                text: 'Unable to load deals. Please retry.' });
        }
    }

    window.loadFollowup = loadFollowup;
    window.loadDeal = loadDeal;
})();
