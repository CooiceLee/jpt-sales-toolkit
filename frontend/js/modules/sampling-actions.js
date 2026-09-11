/** Sampling task form actions. */
(function () {
    'use strict';

    const tr = text => window.I18n?.t(text) || text;
    const taskLocks = new Set();

    const currentTask = index => SamplingFormController.currentTask(index);

    async function refreshSampling(action, message) {
        // The session this task belongs to, captured before the request went
        // out. Reading the current one here would reload whoever the reader has
        // since opened - or the same customer on a later visit - and report our
        // save as theirs.
        if (!await refreshCurrentInquiryData(action.leadId, action)) {
            await refreshNavigationCounts();
            return;
        }
        renderPanelContent('sample');
        await loadSampling();
        const counted = await refreshAllCounts();
        // Those three waits are long enough for the reader to open somebody
        // else; the message and the form belong to whoever is there now.
        if (!InquiryPanelAction.isCurrent(action)) return;
        notify(counted === false ? InquiryPanelAction.countsNotRefreshed() : message);
    }

    // The action is handed in when the caller holds a form: it carries the
    // editor and the button that caller froze, so nothing here has to look up
    // "the save button that is on screen now" - which is how an older save
    // came to unlock the one belonging to the customer opened since.
    async function mutateAndRefresh(mutation, successMessage, failureMessage,
                                    action = InquiryPanelAction.begin()) {
        let committed = false;
        try {
            await mutation();
            committed = true;
            await refreshSampling(action, successMessage);
            return true;
        } catch (error) {
            if (committed) {
                // Written, then the panel could not be re-read. Closing the
                // form is only right if it is still this task's form.
                if (InquiryPanelAction.isCurrent(action)) window.hideSampleTaskForm();
                return InquiryPanelAction.savedButNotRefreshed(error), false;
            }
            if (!InquiryPanelAction.isCurrent(action)) {
                return InquiryPanelAction.failedAfterMovingOn(error), false;
            }
            {
                alert(`${failureMessage}: ${error.message || tr('Unknown error')}`);
            }
            return false;
        }
    }

    window.saveSampleTask = async function() {
        const leadId = State.currentInquiry?.id;
        const index = Number(document.getElementById('sample-task-index').value);
        const task = index >= 0 ? currentTask(index) : null;
        if (!leadId || (!RoleCapabilities.isTech() && !SamplingFormData.requestDescription())) {
            return alert(tr('Please enter a request description.'));
        }
        if (RoleCapabilities.isTech() && (!task || task.archived_at)) {
            return alert(tr('Only an active assigned task result can be updated.'));
        }
        let data;
        try {
            data = SamplingFormData.collect(task);
        } catch (error) {
            return alert(`${tr('Error saving pre-sales task')}: ${tr(error.message || 'Unknown error')}`);
        }
        const save = document.getElementById('sample-task-save');
        if (save?.disabled) return;
        if (save) save.disabled = true;
        // Validated, not already saving: now hold this form and this button.
        const action = InquiryPanelAction.begin({
            editor: 'sample-task-form', button: 'sample-task-save',
        });
        try {
            await mutateAndRefresh(async () => {
                if (task?.id) {
                    await ApiClient.updatePreSalesTask(task.id, {
                        ...data, row_version: task.row_version
                    });
                } else {
                    await ApiClient.createPreSalesTask(leadId, {
                        ...data,
                        client_request_id: SamplingFormData.creationToken()
                    });
                }
            }, tr(task ? 'Pre-sales task updated' : 'Pre-sales task created'),
            tr('Error saving pre-sales task'), action);
        } finally {
            // Gives back the fields and the button this action itself locked,
            // and only while the panel is still the one it started on.
            InquiryPanelAction.release(action);
        }
    };

    window.archiveSampleTask = async function(index) {
        if (!RoleCapabilities.canManageTaskRequests()) return;
        const task = currentTask(index);
        if (!task || !confirm(tr('Archive this pre-sales task?'))) return;
        if (taskLocks.has(task.id)) return;
        taskLocks.add(task.id);
        try {
            await mutateAndRefresh(
                () => ApiClient.archivePreSalesTask(task.id),
                tr('Pre-sales task archived'),
                tr('Error archiving pre-sales task')
            );
        } finally {
            taskLocks.delete(task.id);
        }
    };

    window.restoreSampleTask = async function(index) {
        if (!RoleCapabilities.canManageTaskRequests()) return;
        const task = currentTask(index);
        if (!task) return;
        if (taskLocks.has(task.id)) return;
        taskLocks.add(task.id);
        try {
            await mutateAndRefresh(
                () => ApiClient.restorePreSalesTask(task.id),
                tr('Pre-sales task restored'),
                tr('Error restoring pre-sales task')
            );
        } finally {
            taskLocks.delete(task.id);
        }
    };

    window.newSampleRequest = function() {
        if (!RoleCapabilities.canManageTaskRequests()) return;
        switchModule('sampling');
        notify(tr('Select a lead card, then create the task in the Pre-sales / Sample tab.'));
    };
})();
