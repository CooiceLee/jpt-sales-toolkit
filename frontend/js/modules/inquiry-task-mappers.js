function parseInquiryActivityPayload(activity) {
    try {
        return activity.payload_json ? JSON.parse(activity.payload_json) : {};
    } catch {
        return {};
    }
}

function mapFollowUpActivity(activity) {
    const payload = parseInquiryActivityPayload(activity);
    return {
        id: activity.id,
        method: payload.method || 'Follow-up',
        content: payload.content || activity.summary || '',
        date: activity.created_at,
        response_date: payload.response_date || null,
        customer_feedback: payload.customer_feedback || '',
        next_action: payload.next_action || '',
        next_action_date: payload.next_action_date || null,
        status: payload.status || 'completed',
        actor_name: activity.actor_name || ''
    };
}

function mapAfterSalesTask(task) {
    return {
        id: task.id,
        issue_type: task.issue_type || 'Technical',
        issue_description: task.issue_description || task.summary || '',
        issue_date: task.created_at,
        status: task.status || 'Open',
        assignee_id: task.assignee_id || '',
        technician: task.assignee_name || '',
        solution: task.solution || '',
        customer_satisfaction: task.customer_satisfaction || '',
        lessons_learned: task.lessons_learned || '',
        remarks: task.remarks || '',
        row_version: task.row_version
    };
}
