window.saveAfterSales = async function() {
    const desc = document.getElementById('as-description').value.trim();
    if (!RoleCapabilities.isTech() && !desc) {
        alert('Please enter description');
        return;
    }

    const leadId = State.currentInquiry?.id;
    if (!leadId) {
        alert('No lead selected');
        return;
    }

    const requestData = {
        issue_type: document.getElementById('as-type').value,
        issue_description: desc,
        status: document.getElementById('as-status').value,
        solution: document.getElementById('as-solution').value || null,
        created_at: document.getElementById('as-date').value || null
    };

    try {
        const index = parseInt(document.getElementById('as-index').value, 10);
        const issue = Number.isInteger(index) && index >= 0
            ? State.currentInquiry?.after_sales?.[index]
            : null;
        if (RoleCapabilities.isTech() && !issue?.id) {
            throw new Error('Only an assigned issue result can be updated.');
        }
        const data = RoleCapabilities.isTech()
            ? { status: requestData.status, solution: requestData.solution }
            : requestData;

        if (issue?.id) {
            if (!issue.row_version) {
                throw new Error('Missing row version. Please refresh and try again.');
            }
            await ApiClient.updateAfterSalesTask(issue.id, {
                ...data,
                row_version: issue.row_version
            });
        } else {
            await ApiClient.createAfterSalesTask(leadId, {
                ...data,
                assignee_id: State.user?.id
            });
        }
        await refreshCurrentInquiryData(leadId);

        renderPanelContent('aftersales');
        await refreshAllCounts();
        notify(issue?.id ? 'Issue updated' : 'Issue logged');
        hideAfterSalesForm();
    } catch (err) {
        console.error('After-sales save error:', err);
        alert('Error saving issue: ' + (err.message || 'Unknown error'));
    }
};

window.archiveAfterSales = async function(index) {
    if (!RoleCapabilities.canManageTaskRequests()) return;
    const issue = State.currentInquiry?.after_sales?.[index];
    if (!issue || !issue.id) return;

    if (!confirm('Archive this after-sales issue?')) return;

    try {
        await ApiClient.archiveAfterSalesTask(issue.id);
        await refreshCurrentInquiryData(State.currentInquiry.id);
        renderPanelContent('aftersales');
        await refreshAllCounts();
    } catch (err) {
        console.error('After-sales archive error:', err);
        alert('Error archiving issue: ' + (err.message || 'Unknown error'));
    }
};
