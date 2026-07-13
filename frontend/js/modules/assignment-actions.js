window.changeLeadOwner = async function() {
    const newOwnerId = document.getElementById('lead-owner-select').value;
    if (!newOwnerId) {
        alert('Please select a new owner');
        return;
    }

    const lead = State.currentInquiry._lead;
    if (newOwnerId === lead.owner_id) {
        notify('Owner unchanged');
        return;
    }

    try {
        await ApiClient.updateLead(lead.id, { owner_id: newOwnerId }, lead.row_version);
        notify('Owner updated');

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Change owner error:', err);
        alert('Error changing owner: ' + (err.message || 'Unknown error'));
    }
};

window.addWatcher = async function() {
    const userId = document.getElementById('watcher-select').value;
    if (!userId) {
        alert('Please select a user');
        return;
    }

    const lead = State.currentInquiry._lead;

    try {
        await ApiClient.addAssignment(lead.id, userId, 'watcher');
        notify('Watcher added');

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Add watcher error:', err);
        alert('Error adding watcher: ' + (err.message || 'Unknown error'));
    }
};

window.addCollaborator = async function() {
    const userId = document.getElementById('collaborator-select').value;
    if (!userId) {
        alert('Please select a user');
        return;
    }

    const lead = State.currentInquiry._lead;

    try {
        await ApiClient.addAssignment(lead.id, userId, 'collaborator');
        notify('Collaborator added');

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Add collaborator error:', err);
        alert('Error adding collaborator: ' + (err.message || 'Unknown error'));
    }
};

window.removeAssignment = async function(assignmentId) {
    if (!confirm('Remove this assignment?')) {
        return;
    }

    const lead = State.currentInquiry._lead;

    try {
        await ApiClient.archiveAssignment(lead.id, assignmentId);
        notify('Assignment removed');

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Remove assignment error:', err);
        alert('Error removing assignment: ' + (err.message || 'Unknown error'));
    }
};

// Load users into assignment dropdowns
