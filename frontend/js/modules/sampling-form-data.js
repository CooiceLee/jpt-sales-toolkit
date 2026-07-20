/** Move values between normalized pre-sales tasks and the edit form. */
(function () {
    'use strict';

    const value = id => document.getElementById(id)?.value?.trim() || '';
    const set = (id, next) => {
        const element = document.getElementById(id);
        if (element) element.value = next || '';
    };
    const date = input => String(input || '').slice(0, 10);

    function populate(task) {
        set('sample-task-status', task?.status || 'Open');
        set('sample-task-due', date(task?.due_date));
        set('sample-task-request-date', date(task?.request_date));
        set('sample-task-params', task?.request_description);
        set('sample-task-decision-maker', task?.customer_decision_maker);
        set('sample-task-quantity', task?.quantity_text);
        set('sample-task-competitor', task?.competitor);
        set('sample-task-key-points', task?.key_points);
        set('sample-task-concerns', task?.concerns);
        set('sample-task-progress', task?.progress_text);
        set('sample-task-next-action', task?.next_action);
        set('sample-task-result-summary', task?.result_summary);
        set('sample-task-notes', task?.supplemental_notes);
        set('sample-task-result', task?.sample_result || 'Pending');
        set('sample-task-report', task?.report_link);
        set('sample-task-confirmed', date(task?.confirmed_date));
    }

    function resultPayload(task) {
        return PreSalesTaskModel.mergeResult(task, {
            progress_text: value('sample-task-progress'),
            next_action: value('sample-task-next-action'),
            result_summary: value('sample-task-result-summary'),
            supplemental_notes: value('sample-task-notes'),
            sample_result: value('sample-task-result') || 'Pending',
            report_link: value('sample-task-report'),
            confirmed_date: value('sample-task-confirmed') || null
        });
    }

    function collect(task) {
        const result = value('sample-task-result') || 'Pending';
        let status = value('sample-task-status') || 'Open';
        if (['Success', 'Failed'].includes(result)) status = 'Completed';
        if (result === 'Cancelled') status = 'Cancelled';
        const data = { status, result_json: JSON.stringify(resultPayload(task)) };
        if (RoleCapabilities.canManageTaskRequests()) {
            data.assignee_id = value('sample-task-assignee') || null;
            data.due_date = value('sample-task-due') || null;
            data.request_json = JSON.stringify(PreSalesTaskModel.mergeRequest(task, {
                request_description: value('sample-task-params'),
                request_date: value('sample-task-request-date') || null,
                customer_decision_maker: value('sample-task-decision-maker'),
                quantity_text: value('sample-task-quantity'),
                competitor: value('sample-task-competitor'),
                key_points: value('sample-task-key-points'),
                concerns: value('sample-task-concerns')
            }));
        }
        return data;
    }

    window.SamplingFormData = {
        populate,
        collect,
        requestDescription: () => value('sample-task-params'),
        creationToken: () => value('sample-task-create-token')
    };
})();
