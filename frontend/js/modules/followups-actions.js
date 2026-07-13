window.saveFollowUp = async function() {
    const content = document.getElementById('fu-content').value.trim();
    if (!content) {
        alert('Please enter content');
        return;
    }

    const leadId = State.currentInquiry?.id;
    if (!leadId) {
        alert('No lead selected');
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
        notify(followUp?.id ? 'Follow-up updated' : 'Follow-up added');
        hideFollowUpForm();
    } catch (err) {
        console.error('Follow-up save error:', err);
        alert('Error saving follow-up: ' + (err.message || 'Unknown error'));
    }
};

window.archiveFollowUp = async function(index) {
    const followUp = State.currentInquiry?.follow_ups?.[index];
    const leadId = State.currentInquiry?.id;
    if (!followUp || !followUp.id || !leadId) return;

    if (!confirm('Archive this follow-up?')) return;

    try {
        await ApiClient.archiveActivity(leadId, followUp.id);
        await refreshCurrentInquiryData(leadId);
        renderPanelContent('followup');
        await refreshAllCounts();
    } catch (err) {
        console.error('Follow-up archive error:', err);
        alert('Error archiving follow-up: ' + (err.message || 'Unknown error'));
    }
};

