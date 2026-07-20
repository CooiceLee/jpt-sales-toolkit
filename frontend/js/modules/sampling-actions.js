/** Sampling task form actions. */
(function () {
    'use strict';

    const tr = text => window.I18n?.t(text) || text;
    const taskLocks = new Set();

    const currentTask = index => SamplingFormController.currentTask(index);

    async function refreshSampling(message) {
        const leadId = State.currentInquiry?.id;
        await refreshCurrentInquiryData(leadId);
        renderPanelContent('sample');
        await loadSampling();
        await refreshAllCounts();
        notify(message);
    }

    async function mutateAndRefresh(mutation, successMessage, failureMessage) {
        let committed = false;
        try {
            await mutation();
            committed = true;
            await refreshSampling(successMessage);
            return true;
        } catch (error) {
            if (committed) {
                window.hideSampleTaskForm();
                alert(`${tr('The change was saved, but the screen could not refresh. Reopen this lead to load the latest data.')} ${error.message || ''}`.trim());
            } else {
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
            tr('Error saving pre-sales task'));
        } finally {
            const currentSave = document.getElementById('sample-task-save');
            if (currentSave) currentSave.disabled = false;
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
