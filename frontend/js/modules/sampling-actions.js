/** Sampling task form actions. */
(function() {
    function currentTask(index) {
        return State.currentInquiry?.sample_tasks?.[index] || null;
    }

    async function loadAssignees(selectedId) {
        const select = document.getElementById('sample-task-assignee');
        if (!select) return;
        const users = await ApiClient.listUsers().catch(() => []);
        const techUsers = users.filter(user => user.role === 'tech' && user.is_active !== false);
        select.innerHTML = '<option value="">Unassigned</option>' + techUsers
            .map(user => `<option value="${user.id}" ${user.id === selectedId ? 'selected' : ''}>${escapeHtml(user.display_name || user.username)}</option>`)
            .join('');
    }

    window.showSampleTaskForm = async function(index = -1) {
        const task = index >= 0 ? currentTask(index) : null;
        document.getElementById('sample-task-form')?.classList.remove('hidden');
        document.getElementById('sample-task-index').value = String(index);
        document.getElementById('sample-task-status').value = task?.status || 'Open';
        document.getElementById('sample-task-due').value = task?.due_date || '';
        document.getElementById('sample-task-params').value = task?.sample_params || '';
        document.getElementById('sample-task-result').value = task?.sample_result || 'Pending';
        document.getElementById('sample-task-report').value = task?.report_link || '';
        document.getElementById('sample-task-confirmed').value = task?.confirmed_date || '';
        document.getElementById('sample-task-save').textContent = task ? 'Update request' : 'Save request';
        await loadAssignees(task?.assignee_id || '');
        document.getElementById('sample-task-form')?.scrollIntoView({ block: 'nearest' });
    };

    window.editSampleTask = index => window.showSampleTaskForm(index);
    window.hideSampleTaskForm = () => document.getElementById('sample-task-form')?.classList.add('hidden');

    async function refreshSampling(message) {
        const leadId = State.currentInquiry?.id;
        await refreshCurrentInquiryData(leadId);
        renderPanelContent('sample');
        await loadSampling();
        await refreshAllCounts();
        notify(message);
    }

    window.saveSampleTask = async function() {
        const leadId = State.currentInquiry?.id;
        const params = document.getElementById('sample-task-params').value.trim();
        if (!leadId || !params) return alert('Please enter sample parameters.');
        const index = Number(document.getElementById('sample-task-index').value);
        const task = index >= 0 ? currentTask(index) : null;
        const result = document.getElementById('sample-task-result').value;
        let taskStatus = document.getElementById('sample-task-status').value;
        if (['Success', 'Failed'].includes(result)) taskStatus = 'Completed';
        if (result === 'Cancelled') taskStatus = 'Cancelled';
        const data = {
            assignee_id: document.getElementById('sample-task-assignee').value || null,
            status: taskStatus,
            due_date: document.getElementById('sample-task-due').value || null,
            request_json: JSON.stringify({ sample_params: params }),
            result_json: JSON.stringify({
                sample_result: result,
                report_link: document.getElementById('sample-task-report').value.trim(),
                confirmed_date: document.getElementById('sample-task-confirmed').value || null
            })
        };
        try {
            if (task?.id) {
                await ApiClient.updatePreSalesTask(task.id, { ...data, row_version: task.row_version });
            } else {
                delete data.result_json;
                delete data.status;
                await ApiClient.createPreSalesTask(leadId, data);
            }
            await refreshSampling(task ? 'Sample request updated' : 'Sample request created');
        } catch (error) {
            alert('Error saving sample request: ' + (error.message || 'Unknown error'));
        }
    };

    window.archiveSampleTask = async function(index) {
        const task = currentTask(index);
        if (!task || !confirm('Archive this sample request?')) return;
        try {
            await ApiClient.archivePreSalesTask(task.id);
            await refreshSampling('Sample request archived');
        } catch (error) {
            alert('Error archiving sample request: ' + (error.message || 'Unknown error'));
        }
    };

    window.restoreSampleTask = async function(index) {
        const task = currentTask(index);
        if (!task) return;
        try {
            await ApiClient.restorePreSalesTask(task.id);
            await refreshSampling('Sample request restored');
        } catch (error) {
            alert('Error restoring sample request: ' + (error.message || 'Unknown error'));
        }
    };

    window.newSampleRequest = function() {
        switchModule('sampling');
        notify('Select a lead card, then create the sample request in the Sample tab.');
    };
})();
