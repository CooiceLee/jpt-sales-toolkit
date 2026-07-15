/** Sampling worklist backed by pre-sales tasks. */
(function() {
    function parseJson(value) {
        if (!value) return {};
        if (typeof value === 'object') return value;
        try { return JSON.parse(value); } catch { return {}; }
    }

    function toView(task) {
        const request = parseJson(task.request_json);
        const result = parseJson(task.result_json);
        return {
            ...task,
            sample_params: request.sample_params || '',
            sample_result: result.sample_result || 'Pending',
            report_link: result.report_link || '',
            confirmed_date: result.confirmed_date || ''
        };
    }

    async function loadWorklist() {
        const filter = State.currentFilters.sampling || 'all';
        try {
            const leadFilters = RoleCapabilities.isTech()
                ? getSharedLeadFilters()
                : { ...getSharedLeadFilters(), sales_stage: 'Following' };
            const [leads, tasks] = await Promise.all([
                ApiClient.listLeads(leadFilters),
                ApiClient.listPreSalesTasks()
            ]);
            const latestByLead = new Map();
            tasks.map(toView).forEach(task => {
                if (!latestByLead.has(task.lead_id)) latestByLead.set(task.lead_id, task);
            });
            let items = leads.map(lead => {
                const task = latestByLead.get(lead.id);
                return leadToCardItem(lead, {
                    sample_status: task?.status || 'Not Requested',
                    sample_result: task?.sample_result || 'Pending',
                    pre_sales_owner: task?.assignee_name || '',
                    sample_due_date: task?.due_date || '',
                    _sampleTask: task || null
                });
            }).filter(item => !RoleCapabilities.isTech() || item._sampleTask);
            if (filter !== 'all') items = items.filter(item => item.sample_status === filter);
            setText('sampling-count', `${items.length} samples`);
            renderCards('sampling-cards', items, 'sampling');
        } catch (error) {
            console.error('Sampling error:', error);
            setText('sampling-count', '0 samples');
            renderCards('sampling-cards', [], 'sampling');
        }
    }

    function renderTab(inquiry) {
        return SamplingPanel.render(inquiry);
    }

    window.SamplingModule = { toView, renderTab };
    window.loadSampling = loadWorklist;
})();
