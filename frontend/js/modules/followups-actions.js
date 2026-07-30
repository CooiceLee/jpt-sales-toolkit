function followupActionText(text, params = {}) {
    return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
}

window.saveFollowUp = async function() {
    const content = document.getElementById('fu-content').value.trim();
    if (!content) {
        alert(followupActionText('Please enter follow-up content.'));
        return;
    }

    const leadId = State.currentInquiry?.id;
    if (!leadId) {
        alert(followupActionText('No lead selected.'));
        return;
    }

    const data = {
        method: document.getElementById('fu-method').value,
        content: content,
        status: document.getElementById('fu-status').value || 'pending',
        created_at: document.getElementById('fu-date').value || null,
        response_date: document.getElementById('fu-response').value || null,
        customer_feedback: document.getElementById('fu-feedback').value,
        next_action: document.getElementById('fu-next').value,
        next_action_date: document.getElementById('fu-next-date').value || null,
        visibility: 'all'
    };

    const saveButton = document.getElementById('fu-save-btn');
    if (saveButton?.disabled) return;
    if (saveButton) saveButton.disabled = true;
    try {
        const index = parseInt(document.getElementById('fu-index').value, 10);
        const followUp = Number.isInteger(index) && index >= 0
            ? State.currentInquiry?.follow_ups?.[index]
            : null;

        if (followUp?.id) {
            await ApiClient.updateActivity(leadId, followUp.id, data);
        } else {
            await ApiClient.addFollowUp(leadId, data);
        }
        await refreshCurrentInquiryData(leadId);

        renderPanelContent('followup');
        await refreshAllCounts();
        notify(followUp?.id
            ? followupActionText('Follow-up updated.')
            : followupActionText('Follow-up added.'));
        hideFollowUpForm();
    } catch (err) {
        console.error('Follow-up save error:', err);
        alert(followupActionText('Error saving follow-up: {error}', {
            error: followupActionText(err?.message || 'Unknown error')
        }));
    } finally {
        const currentButton = document.getElementById('fu-save-btn');
        if (currentButton) currentButton.disabled = false;
    }
};

window.archiveFollowUp = async function(index) {
    const followUp = State.currentInquiry?.follow_ups?.[index];
    const leadId = State.currentInquiry?.id;
    if (!followUp || !followUp.id || !leadId) return;

    if (!confirm(followupActionText('Archive this follow-up?'))) return;

    try {
        await ApiClient.archiveActivity(leadId, followUp.id);
        await refreshCurrentInquiryData(leadId);
        renderPanelContent('followup');
        await refreshAllCounts();
    } catch (err) {
        console.error('Follow-up archive error:', err);
        alert(followupActionText('Error archiving follow-up: {error}', {
            error: followupActionText(err?.message || 'Unknown error')
        }));
    }
};
