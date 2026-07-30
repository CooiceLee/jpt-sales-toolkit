window.changeLeadOwner = async function() {
    const newOwnerId = document.getElementById('lead-owner-select').value;
    if (!newOwnerId) {
        alert(I18n.t('Please select a new owner'));
        return;
    }

    const lead = State.currentInquiry._lead;
    if (newOwnerId === lead.owner_id) {
        notify(I18n.t('Owner unchanged'));
        return;
    }

    try {
        await ApiClient.updateLead(lead.id, { owner_id: newOwnerId }, lead.row_version);
        notify(I18n.t('Owner updated'));

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Change owner error:', err);
        alert(I18n.t('Error changing owner: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};

window.addWatcher = async function() {
    const userId = document.getElementById('watcher-select').value;
    if (!userId) {
        alert(I18n.t('Please select a user'));
        return;
    }

    const lead = State.currentInquiry._lead;

    try {
        await ApiClient.addAssignment(lead.id, userId, 'watcher');
        notify(I18n.t('Watcher added'));

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Add watcher error:', err);
        alert(I18n.t('Error adding watcher: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};

window.addCollaborator = async function() {
    const userId = document.getElementById('collaborator-select').value;
    if (!userId) {
        alert(I18n.t('Please select a user'));
        return;
    }

    const lead = State.currentInquiry._lead;

    try {
        await ApiClient.addAssignment(lead.id, userId, 'collaborator');
        notify(I18n.t('Collaborator added'));

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Add collaborator error:', err);
        alert(I18n.t('Error adding collaborator: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};

window.removeAssignment = async function(assignmentId) {
    if (!confirm(I18n.t('Remove this assignment?'))) {
        return;
    }

    const lead = State.currentInquiry._lead;

    try {
        await ApiClient.archiveAssignment(lead.id, assignmentId);
        notify(I18n.t('Assignment removed'));

        // Refresh lead
        const refreshed = await ApiClient.getLead(lead.id);
        State.currentInquiry._lead = refreshed;
        renderPanelContent('basic');
    } catch (err) {
        console.error('Remove assignment error:', err);
        alert(I18n.t('Error removing assignment: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};

// Load users into assignment dropdowns
