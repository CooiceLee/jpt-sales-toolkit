function afterSalesActionText(text, params = {}) {
    return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
}

window.saveAfterSales = async function() {
    const desc = document.getElementById('as-description').value.trim();
    if (!RoleCapabilities.isTech() && !desc) {
        alert(afterSalesActionText('Please enter an issue description.'));
        return;
    }

    const leadId = State.currentInquiry?.id;
    if (!leadId) {
        alert(afterSalesActionText('No lead selected.'));
        return;
    }

    const requestData = {
        issue_type: document.getElementById('as-type').value,
        issue_description: desc,
        status: document.getElementById('as-status').value,
        solution: document.getElementById('as-solution').value || null,
        customer_satisfaction: document.getElementById('as-satisfaction').value || null,
        lessons_learned: document.getElementById('as-lessons').value || null,
        remarks: document.getElementById('as-remarks').value || null,
        created_at: document.getElementById('as-date').value || null
    };

    const saveButton = document.getElementById('as-save-btn');
    if (saveButton?.disabled) return;
    if (saveButton) saveButton.disabled = true;
    try {
        const index = parseInt(document.getElementById('as-index').value, 10);
        const issue = Number.isInteger(index) && index >= 0
            ? State.currentInquiry?.after_sales?.[index]
            : null;
        if (RoleCapabilities.isTech() && !issue?.id) {
            throw new Error(afterSalesActionText('Only an assigned issue result can be updated.'));
        }
        const data = RoleCapabilities.isTech()
            ? {
                status: requestData.status,
                solution: requestData.solution,
                customer_satisfaction: requestData.customer_satisfaction,
                lessons_learned: requestData.lessons_learned,
                remarks: requestData.remarks
            }
            : requestData;

        if (issue?.id) {
            if (!issue.row_version) {
                throw new Error(afterSalesActionText('Missing row version. Please refresh and try again.'));
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
        notify(issue?.id
            ? afterSalesActionText('Issue updated.')
            : afterSalesActionText('Issue logged.'));
        hideAfterSalesForm();
    } catch (err) {
        console.error('After-sales save error:', err);
        alert(afterSalesActionText('Error saving issue: {error}', {
            error: afterSalesActionText(err?.message || 'Unknown error')
        }));
    } finally {
        const currentButton = document.getElementById('as-save-btn');
        if (currentButton) currentButton.disabled = false;
    }
};

window.archiveAfterSales = async function(index) {
    if (!RoleCapabilities.canManageTaskRequests()) return;
    const issue = State.currentInquiry?.after_sales?.[index];
    if (!issue || !issue.id) return;

    if (!confirm(afterSalesActionText('Archive this after-sales issue?'))) return;

    try {
        await ApiClient.archiveAfterSalesTask(issue.id);
        await refreshCurrentInquiryData(State.currentInquiry.id);
        renderPanelContent('aftersales');
        await refreshAllCounts();
    } catch (err) {
        console.error('After-sales archive error:', err);
        alert(afterSalesActionText('Error archiving issue: {error}', {
            error: afterSalesActionText(err?.message || 'Unknown error')
        }));
    }
};
