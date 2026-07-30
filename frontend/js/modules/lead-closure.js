function canCloseLead(lead) {
    if (!lead || State.user?.role === 'tech') return false;
    return State.user?.role === 'leader' || lead.owner_id === State.user?.id;
}

function renderLeadClosureSection(inq) {
    const lead = inq?._lead;
    if (!canCloseLead(lead)) return '';

    const isClosed = lead?.sales_stage === 'Lost';
    const note = lead?.lost_reason_text || '';
    return `
        <div class="lead-close-section">
            <h3>Close Lead</h3>
            <p class="lead-close-help">Use this when the lead will not move to the next workflow. Closed leads are grouped under Deal / Lost.</p>
            <div class="lead-close-grid">
                <input type="text" class="form-input" id="lead-close-reason-code" placeholder="Reason tag" value="${escapeHtml(lead?.lost_reason_code || '')}">
                <input type="text" class="form-input" id="lead-close-reason-text" placeholder="Reason details" value="${escapeHtml(note)}">
            </div>
            <div class="lead-close-actions">
                <button type="button" class="btn btn-secondary" onclick="closeCurrentLead()">${isClosed ? 'Update close note' : 'Close lead'}</button>
                ${isClosed ? '<span class="lead-close-state">Current status: Lost</span>' : ''}
            </div>
        </div>
    `;
}

window.closeCurrentLead = async function() {
    const lead = State.currentInquiry?._lead;
    if (!lead?.id) return;

    const reasonCode = document.getElementById('lead-close-reason-code')?.value?.trim() || null;
    const reasonText = document.getElementById('lead-close-reason-text')?.value?.trim() || null;
    if (!reasonCode && !reasonText) {
        alert(I18n.t('Enter a close reason before closing the lead.'));
        return;
    }

    try {
        await ApiClient.updateLead(lead.id, {
            sales_stage: 'Lost',
            lost_reason_code: reasonCode,
            lost_reason_text: reasonText
        }, lead.row_version);
        await refreshCurrentInquiryData(lead.id);
        State.currentInquiry.stage = 'Lost';
        notify(I18n.t('Lead closed and grouped under Deal / Lost'));
        renderPanelTabs('deal');
        await refreshAllCounts();
    } catch (err) {
        console.error('Close lead error:', err);
        if (err.name === 'ConflictError') {
            alert(I18n.t('This lead was updated by another user. Refresh and try again.'));
            return;
        }
        alert(I18n.t('Error closing lead: {error}', {
            error: I18n.t(err.message || 'Unknown error')
        }));
    }
};
