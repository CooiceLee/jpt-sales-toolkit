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
            sample_status: task?.status || '',
            sample_result: task?.sample_result || '',
            pre_sales_owner: task?.assignee_name || '',
            sample_due_date: task?.due_date || '',
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
        try {
            const [leads, rawTasks] = await Promise.all([
                ApiClient.listLeads({
                    ...getSharedLeadFilters(),
                    limit: 100000
                }),
                ApiClient.listPreSalesTasks({ limit: 100000 })
            ]);
            const tasks = rawTasks.map(PreSalesTaskModel.toView);
            const filteredTasks = filter === 'all'
                ? tasks
                : tasks.filter(task => task.status === filter);
            const tasksByLead = new Map();
            filteredTasks.forEach(task => {
                const group = tasksByLead.get(task.lead_id) || [];
                group.push(task);
                tasksByLead.set(task.lead_id, group);
            });
            const items = leads
                .filter(lead => tasksByLead.has(lead.id))
                .map(lead => cardItem(lead, tasksByLead.get(lead.id)));
            const displayedTaskCount = items.reduce(
                (total, item) => total + item._sampleTasks.length, 0
            );
            setText('sampling-count', tr('{leadCount} leads · {taskCount} tasks', {
                leadCount: items.length,
                taskCount: displayedTaskCount
            }));
            renderCards('sampling-cards', items, 'sampling');
        } catch (error) {
            console.error('Pre-sales worklist error:', error);
            setText('sampling-count', tr('Unable to load'));
            setPanelError(
                'sampling-cards',
                tr('Unable to load pre-sales tasks. Please retry.')
            );
        }
    }

    window.SamplingModule = {
        toView: PreSalesTaskModel.toView,
        renderTab: inquiry => SamplingPanel.render(inquiry)
    };
    window.loadSampling = loadWorklist;
})();
