/** Pre-sales / sampling worklist backed only by actual pre-sales task records. */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const activeStatuses = new Set(['Open', 'In Progress']);

    function newestFirst(left, right) {
        const leftDate = Date.parse(left.updated_at || left.created_at || 0) || 0;
        const rightDate = Date.parse(right.updated_at || right.created_at || 0) || 0;
        return rightDate - leftDate;
    }

    function representative(tasks) {
        const active = tasks.filter(task => activeStatuses.has(task.status)).sort(newestFirst);
        return active[0] || [...tasks].sort(newestFirst)[0] || null;
    }

    function cardItem(lead, tasks) {
        const task = representative(tasks);
        const latestFollowUp = lead.latest_follow_up || {};
        return leadToCardItem(lead, {
            deal_amount: lead.deal_amount ?? null,
            estimated_value: lead.estimated_value ?? null,
            sample_status: task?.status || '',
            sample_result: task?.sample_result || '',
            pre_sales_owner: task?.assignee_name || '',
            sample_due_date: task?.due_date || '',
            sample_task_updated_at: task?.updated_at || task?.created_at || '',
            sample_progress: task?.progress_text || '',
            sample_next_action: task?.next_action || '',
            sample_request: task?.request_description || '',
            latest_follow_up_at: lead.latest_follow_up_at
                || latestFollowUp.created_at || '',
            latest_follow_up_at_raw: latestFollowUp.occurred_at_raw || '',
            latest_follow_up_summary: lead.latest_follow_up_summary
                || latestFollowUp.content || latestFollowUp.summary || '',
            sample_task_count: tasks.length,
            _sampleTask: task,
            _sampleTasks: tasks
        });
    }

    async function loadWorklist() {
        const filter = State.currentFilters.sampling || 'all';
        const request = WorklistRequest.begin('sampling');
        try {
            // Read page by page. An enormous limit only moves the cliff to a
            // number nobody is watching, and the queue silently loses whatever
            // falls past it.
            const [leadPage, taskPage] = await Promise.all([
                ApiClient.listAllLeads(getSharedLeadFilters()),
                ApiClient.listAllPreSalesTasks()
            ]);
            if (!WorklistRequest.isCurrent(request)) return;
            const leads = leadPage.items;
            const tasks = taskPage.items.map(PreSalesTaskModel.toView);
            const filteredTasks = filter === 'all'
                ? tasks
                : tasks.filter(task => task.status === filter);
            const tasksByLead = new Map();
            filteredTasks.forEach(task => {
                const group = tasksByLead.get(task.lead_id) || [];
                group.push(task);
                tasksByLead.set(task.lead_id, group);
            });
            const items = WorklistSort.sampling(leads
                .filter(lead => tasksByLead.has(lead.id))
                .map(lead => cardItem(lead, tasksByLead.get(lead.id))));
            const displayedTaskCount = items.reduce(
                (total, item) => total + item._sampleTasks.length, 0
            );
            setText('sampling-count', [
                tr('{leadCount} leads · {taskCount} tasks', {
                    leadCount: items.length,
                    taskCount: displayedTaskCount,
                }),
                PagedFetch.note(leadPage, taskPage),
            ].filter(Boolean).join(' · '));
            SamplingWorkbench.render(items);
        } catch (error) {
            console.error('Pre-sales worklist error:', error);
            if (!WorklistRequest.isCurrent(request)) return;
            setText('sampling-count', tr('Unable to load'));
            SamplingWorkbench.render([], {
                title: 'Unable to load',
                text: 'Unable to load pre-sales tasks. Please retry.',
            });
        }
    }

    window.SamplingModule = {
        toView: PreSalesTaskModel.toView,
        renderTab: inquiry => SamplingPanel.render(inquiry)
    };
    window.loadSampling = loadWorklist;
})();
