/** Open, populate and protect the pre-sales task form. */
(function () {
    'use strict';

    const tr = text => window.I18n?.t(text) || text;
    const currentTask = index => State.currentInquiry?.sample_tasks?.[index] || null;
    const requestId = () => window.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(16).slice(2)}`;

    async function loadAssignees(selectedId, selectedName) {
        const select = document.getElementById('sample-task-assignee');
        if (!select) return false;
        let users;
        try {
            users = await ApiClient.listUsers();
        } catch {
            select.innerHTML = selectedId
                ? `<option value="${escapeHtml(selectedId)}" selected>${escapeHtml(selectedName || tr('Current assignee'))}</option>`
                : `<option value="">${escapeHtml(tr('Unassigned'))}</option>`;
            select.disabled = true;
            alert(tr('Unable to load pre-sales owners. The current assignment was preserved.'));
            return Boolean(selectedId);
        }
        const techUsers = users.filter(user => user.role === 'tech' && user.is_active !== false);
        const selectedIsActive = techUsers.some(user => user.id === selectedId);
        const preserved = selectedId && !selectedIsActive
            ? `<option value="${escapeHtml(selectedId)}" selected>${escapeHtml(
                `${selectedName || tr('Current assignee')} (${tr('Inactive')})`
            )}</option>`
            : '';
        select.disabled = false;
        select.innerHTML = `<option value="">${escapeHtml(tr('Unassigned'))}</option>` + techUsers
            .map(user => `<option value="${escapeHtml(user.id)}" ${user.id === selectedId ? 'selected' : ''}>${escapeHtml(user.display_name || user.username)}</option>`)
            .join('') + preserved;
        return true;
    }

    window.showSampleTaskForm = async function (index = -1) {
        const task = index >= 0 ? currentTask(index) : null;
        if (RoleCapabilities.isTech() && (!task || task.archived_at)) return;
        const payloadSafe = !task || (
            task._result_valid !== false
            && (!RoleCapabilities.canManageTaskRequests() || task._request_valid !== false)
        );
        const form = document.getElementById('sample-task-form');
        const save = document.getElementById('sample-task-save');
        if (save) save.disabled = true;
        document.getElementById('sample-task-index').value = String(index);
        document.getElementById('sample-task-create-token').value = task ? '' : requestId();
        SamplingFormData.populate(task);
        if (save) {
            save.textContent = tr(RoleCapabilities.isTech()
                ? 'Save result'
                : (task ? 'Update task' : 'Save task'));
        }
        const ready = RoleCapabilities.isTech()
            || await loadAssignees(task?.assignee_id || '', task?.assignee_name || '');
        if (save) save.disabled = !ready || !payloadSafe;
        if (!payloadSafe) {
            alert(tr('This task contains damaged JSON data. Repair or re-import it before saving.'));
        }
        form?.classList.remove('hidden');
        form?.scrollIntoView({ block: 'nearest' });
    };

    window.editSampleTask = index => window.showSampleTaskForm(index);
    window.hideSampleTaskForm = () =>
        document.getElementById('sample-task-form')?.classList.add('hidden');
    window.SamplingFormController = { currentTask };
})();
