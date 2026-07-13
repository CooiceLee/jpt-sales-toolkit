async function loadAssignmentUsers() {
    try {
        const users = await ApiClient.listUsers();
        const lead = State.currentInquiry?._lead;
        if (!lead) return;

        // Populate owner select
        const ownerSelect = document.getElementById('lead-owner-select');
        if (ownerSelect) {
            ownerSelect.innerHTML = '<option value="">Select owner...</option>' +
                users.map(u => `<option value="${u.id}" ${u.id === lead.owner_id ? 'selected' : ''}>${escapeHtml(u.display_name)}</option>`).join('');
        }

        // Populate watcher select (exclude current assignments)
        const watcherSelect = document.getElementById('watcher-select');
        if (watcherSelect) {
            const assignments = lead.assignments || [];
            const assignedIds = assignments.map(a => a.user_id);
            const availableUsers = users.filter(u => !assignedIds.includes(u.id));

            watcherSelect.innerHTML = '<option value="">Add watcher...</option>' +
                availableUsers.map(u => `<option value="${u.id}">${escapeHtml(u.display_name)}</option>`).join('');
        }

        // Populate collaborator select (exclude current assignments)
        const collaboratorSelect = document.getElementById('collaborator-select');
        if (collaboratorSelect) {
            const assignments = lead.assignments || [];
            const assignedIds = assignments.map(a => a.user_id);
            const availableUsers = users.filter(u => !assignedIds.includes(u.id));

            collaboratorSelect.innerHTML = '<option value="">Add collaborator...</option>' +
                availableUsers.map(u => `<option value="${u.id}">${escapeHtml(u.display_name)}</option>`).join('');
        }
    } catch (err) {
        console.error('Load users error:', err);
    }
}

