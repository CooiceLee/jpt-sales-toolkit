window.showFollowUpForm = function() {
    document.getElementById('followup-form').classList.remove('hidden');
    // With nothing being written, the history reads better across the whole
    // panel than beside an empty column.
    document.querySelector('.followup-panel-grid')?.classList.add('has-open-form');
    document.getElementById('fu-index').value = '-1';
    document.getElementById('fu-date').value = new Date().toISOString().slice(0, 16);
    document.getElementById('fu-method').value = 'Email';
    document.getElementById('fu-content').value = '';
    document.getElementById('fu-status').value = 'pending';
    document.getElementById('fu-response').value = '';
    document.getElementById('fu-feedback').value = '';
    document.getElementById('fu-next').value = '';
    document.getElementById('fu-next-date').value = '';
    const saveBtn = document.getElementById('fu-save-btn');
    if (saveBtn) saveBtn.textContent = 'Save';
};

window.hideFollowUpForm = function() {
    document.getElementById('followup-form').classList.add('hidden');
    document.querySelector('.followup-panel-grid')?.classList.remove('has-open-form');
    window.PanelDirtyState?.reset?.();
};

window.editFollowUp = function(index) {
    const fu = State.currentInquiry?.follow_ups?.[index];
    if (!fu) return;

    document.getElementById('followup-form').classList.remove('hidden');
    document.querySelector('.followup-panel-grid')?.classList.add('has-open-form');
    document.getElementById('fu-index').value = index;
    document.getElementById('fu-date').value = fu.date?.slice(0, 16) || '';
    document.getElementById('fu-method').value = fu.method || 'Email';
    document.getElementById('fu-content').value = fu.content || '';
    document.getElementById('fu-status').value = fu.status || 'pending';
    document.getElementById('fu-response').value = fu.response_date?.slice(0, 16) || '';
    document.getElementById('fu-feedback').value = fu.customer_feedback || '';
    document.getElementById('fu-next').value = fu.next_action || '';
    document.getElementById('fu-next-date').value = fu.next_action_date || '';
    const saveBtn = document.getElementById('fu-save-btn');
    if (saveBtn) saveBtn.textContent = 'Update';
    document.getElementById('followup-form')?.scrollIntoView({ block: 'nearest' });
};

async function refreshCurrentInquiryData(leadId, action) {
    // The panel belongs to the visit the reader is on, not merely to a
    // customer id: open A, start saving, look at B, come back to A, and the id
    // matches again while the draft on screen is a different one. An action
    // carries the session it began in, and returning false says the answer
    // arrived too late to be applied.
    const fresh = await InquiryPanelData.load(leadId);
    if (action) {
        if (!window.InquiryPanelAction?.isCurrent?.(action)) return false;
    } else if (State.currentInquiry && State.currentInquiry.id !== leadId) {
        return false;
    }
    State.currentInquiry = fresh;
    return true;
}
