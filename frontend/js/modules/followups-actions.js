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
    // The form is held for the length of the request: what was submitted is
    // what is on screen, and anything typed afterwards would be neither sent
    // nor kept. The action holds the form and the button it locked, so the
    // release cannot reach a form belonging to somebody else.
    const action = InquiryPanelAction.begin({
        editor: 'followup-form', button: 'fu-save-btn',
    });
    let written = false;
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
        written = true;
        const stillHere = await refreshCurrentInquiryData(leadId, action);
        if (!stillHere) {
            // Saved, and the reader has moved on. The numbers are theirs to
            // update; the panel in front of them is not ours to touch.
            await refreshNavigationCounts();
            return;
        }
        renderPanelContent('followup');
        // refreshAllCounts keeps its own failures to itself and answers with
        // false. Ignoring that told the reader everything was up to date while
        // the numbers on the left were still the old ones.
        const counted = await refreshAllCounts();
        // Checked again: the counts took a moment, and the reader may have
        // opened somebody else while they did. Their form is not ours to close.
        if (!InquiryPanelAction.isCurrent(action)) return;
        notify(counted === false ? InquiryPanelAction.countsNotRefreshed()
            : followUp?.id
                ? followupActionText('Follow-up updated.')
                : followupActionText('Follow-up added.'));
        hideFollowUpForm();
    } catch (err) {
        // Written but not redrawn is not a failed save, and must never send
        // somebody to record the same follow-up twice.
        if (written) return InquiryPanelAction.savedButNotRefreshed(err);
        if (!InquiryPanelAction.isCurrent(action)) {
            return InquiryPanelAction.failedAfterMovingOn(err);
        }
        console.error('Follow-up save error:', err);
        alert(followupActionText('Error saving follow-up: {error}', {
            error: followupActionText(err?.message || 'Unknown error')
        }));
    } finally {
        InquiryPanelAction.release(action);
    }
};

window.archiveFollowUp = async function(index) {
    const followUp = State.currentInquiry?.follow_ups?.[index];
    const leadId = State.currentInquiry?.id;
    if (!followUp || !followUp.id || !leadId) return;

    if (!confirm(followupActionText('Archive this follow-up?'))) return;

    const action = InquiryPanelAction.begin();
    let archived = false;
    try {
        await ApiClient.archiveActivity(leadId, followUp.id);
        archived = true;
        if (!await refreshCurrentInquiryData(leadId, action)) {
            await refreshNavigationCounts();
            return;
        }
        renderPanelContent('followup');
        if (await refreshAllCounts() === false && InquiryPanelAction.isCurrent(action)) {
            notify(InquiryPanelAction.countsNotRefreshed());
        }
    } catch (err) {
        // Archived, then the re-read failed: saying "could not archive" sends
        // somebody to archive it a second time.
        if (archived) return InquiryPanelAction.archivedButNotRefreshed(err);
        if (!InquiryPanelAction.isCurrent(action)) {
            return InquiryPanelAction.failedAfterMovingOn(err);
        }
        console.error('Follow-up archive error:', err);
        alert(followupActionText('Error archiving follow-up: {error}', {
            error: followupActionText(err?.message || 'Unknown error')
        }));
    }
};
