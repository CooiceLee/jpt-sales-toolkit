window.showFollowUpForm = function() {
    document.getElementById('followup-form').classList.remove('hidden');
    document.getElementById('fu-index').value = '-1';
    document.getElementById('fu-date').value = new Date().toISOString().slice(0, 16);
    document.getElementById('fu-method').value = 'Email';
    document.getElementById('fu-content').value = '';
    document.getElementById('fu-status').value = 'pending';
    document.getElementById('fu-response').value = '';
    document.getElementById('fu-feedback').value = '';
    document.getElementById('fu-next').value = '';
    document.getElementById('fu-next-date').value = '';
    const saveBtn = document.getElementById('fu-save-btn');
    if (saveBtn) saveBtn.textContent = 'Save';
};

window.hideFollowUpForm = function() {
    document.getElementById('followup-form').classList.add('hidden');
};

window.editFollowUp = function(index) {
    const fu = State.currentInquiry?.follow_ups?.[index];
    if (!fu) return;

    document.getElementById('followup-form').classList.remove('hidden');
    document.getElementById('fu-index').value = index;
    document.getElementById('fu-date').value = fu.date?.slice(0, 16) || '';
    document.getElementById('fu-method').value = fu.method || 'Email';
    document.getElementById('fu-content').value = fu.content || '';
    document.getElementById('fu-status').value = fu.status || 'pending';
    document.getElementById('fu-response').value = fu.response_date?.slice(0, 16) || '';
    document.getElementById('fu-feedback').value = fu.customer_feedback || '';
    document.getElementById('fu-next').value = fu.next_action || '';
    document.getElementById('fu-next-date').value = fu.next_action_date || '';
    const saveBtn = document.getElementById('fu-save-btn');
    if (saveBtn) saveBtn.textContent = 'Update';
    document.getElementById('followup-form')?.scrollIntoView({ block: 'nearest' });
};

async function refreshCurrentInquiryData(leadId) {
    const taskOnly = RoleCapabilities.isTech();
    const [lead, activities, preSalesTasks, afterSalesTasks, attachments] = await Promise.all([
        ApiClient.getLead(leadId),
        taskOnly ? [] : ApiClient.listActivities(leadId).catch(() => []),
        ApiClient.listPreSalesTasks({ lead_id: leadId, include_archived: true }).catch(() => []),
        ApiClient.listAfterSalesTasks({ lead_id: leadId }).catch(() => []),
        taskOnly ? [] : ApiClient.listAttachments(leadId).catch(() => [])
    ]);

    State.currentInquiry._lead = lead;
    State.currentInquiry._customer = lead.customer;
    State.currentInquiry.row_version = lead.row_version;
    State.currentInquiry._activities = activities;
    State.currentInquiry._preSalesTasks = preSalesTasks;
    State.currentInquiry._afterSalesTasks = afterSalesTasks;
    State.currentInquiry._attachments = attachments;
    State.currentInquiry.attachments = attachments;
    State.currentInquiry.sample_tasks = preSalesTasks.map(task => SamplingModule.toView(task));
    State.currentInquiry.follow_ups = activities
        .filter(a => a.action_type === 'follow_up')
        .map(mapFollowUpActivity);
    State.currentInquiry.after_sales = afterSalesTasks.map(mapAfterSalesTask);
}
