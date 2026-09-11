function afterSalesActionText(text, params = {}) {
    return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
}

window.saveAfterSales = async function() {
    let written = false;
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

    // Order matters, and getting it wrong stopped the save from happening at
    // all: the freeze disables every control inside the form - the save button
    // among them - so a "is this already submitting?" check made after it
    // always said yes, and the function returned before sending anything and
    // before the finally that would have given the fields back. Validate
    // first, then ask whether a save is already in flight, and only then take
    // the freeze - with every path after it inside the try/finally.
    const saveButton = document.getElementById('as-save-btn');
    if (saveButton?.disabled) return;
    if (saveButton) saveButton.disabled = true;
    const action = InquiryPanelAction.begin({
        editor: 'aftersales-form', button: 'as-save-btn',
    });
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
        written = true;
        if (!await refreshCurrentInquiryData(leadId, action)) {
            await refreshNavigationCounts();
            return;
        }
        renderPanelContent('aftersales');
        // refreshAllCounts keeps its own failures to itself and answers with
        // false. Ignoring that told the reader everything was up to date while
        // the numbers on the left were still the old ones.
        const counted = await refreshAllCounts();
        if (!InquiryPanelAction.isCurrent(action)) return;
        notify(counted === false ? InquiryPanelAction.countsNotRefreshed()
            : issue?.id
                ? afterSalesActionText('Issue updated.')
                : afterSalesActionText('Issue logged.'));
        hideAfterSalesForm();
    } catch (err) {
        // Logged but not redrawn is not a failed save, and must never send
        // somebody to log the same issue twice.
        if (written) return InquiryPanelAction.savedButNotRefreshed(err);
        if (!InquiryPanelAction.isCurrent(action)) {
            return InquiryPanelAction.failedAfterMovingOn(err);
        }
        console.error('After-sales save error:', err);
        alert(afterSalesActionText('Error saving issue: {error}', {
            error: afterSalesActionText(err?.message || 'Unknown error')
        }));
    } finally {
        InquiryPanelAction.release(action);
    }
};

window.archiveAfterSales = async function(index) {
    if (!RoleCapabilities.canManageTaskRequests()) return;
    const issue = State.currentInquiry?.after_sales?.[index];
    if (!issue || !issue.id) return;

    if (!confirm(afterSalesActionText('Archive this after-sales issue?'))) return;

    // Captured before the request: after it, the reader may be elsewhere.
    const leadId = State.currentInquiry.id;
    const action = InquiryPanelAction.begin();
    let archived = false;
    try {
        await ApiClient.archiveAfterSalesTask(issue.id);
        archived = true;
        if (!await refreshCurrentInquiryData(leadId, action)) {
            await refreshNavigationCounts();
            return;
        }
        renderPanelContent('aftersales');
        if (await refreshAllCounts() === false && InquiryPanelAction.isCurrent(action)) {
            notify(InquiryPanelAction.countsNotRefreshed());
        }
    } catch (err) {
        if (archived) return InquiryPanelAction.archivedButNotRefreshed(err);
        if (!InquiryPanelAction.isCurrent(action)) {
            return InquiryPanelAction.failedAfterMovingOn(err);
        }
        console.error('After-sales archive error:', err);
        alert(afterSalesActionText('Error archiving issue: {error}', {
            error: afterSalesActionText(err?.message || 'Unknown error')
        }));
    }
};
