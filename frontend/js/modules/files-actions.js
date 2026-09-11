function fileActionText(text, params = {}) {
    return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
}

window.saveAttachment = async function() {
    let written = false;
    const leadId = State.currentInquiry?.id;
    const fileInput = document.getElementById('attachment-file');
    const category = document.getElementById('attachment-category')?.value || 'other';
    const name = document.getElementById('attachment-name')?.value.trim() || '';
    const versionRaw = document.getElementById('attachment-version')?.value || '1';
    const versionNo = parseInt(versionRaw, 10);
    const file = fileInput?.files?.[0];
    const index = parseInt(document.getElementById('attachment-index')?.value || '-1', 10);
    const attachment = Number.isInteger(index) && index >= 0
        ? State.currentInquiry?.attachments?.[index]
        : null;

    if (!leadId) {
        alert(fileActionText('No lead selected.'));
        return;
    }
    if (!Number.isInteger(versionNo) || versionNo < 1) {
        alert(fileActionText('Version must be a positive number.'));
        return;
    }
    if (!attachment && !file) {
        alert(fileActionText('Please choose a file.'));
        return;
    }

    // Validate, then check for a save already in flight, then freeze. Taking
    // the freeze first disabled the save button, so the check below saw its
    // own doing and returned - no request, and no finally to unfreeze.
    const saveButton = document.getElementById('attachment-save-btn');
    if (saveButton?.disabled) return;
    if (saveButton) saveButton.disabled = true;
    const action = InquiryPanelAction.begin({
        editor: 'attachment-form', button: 'attachment-save-btn',
    });
    try {
        if (attachment?.id) {
            await ApiClient.updateAttachment(leadId, attachment.id, {
                category,
                version_no: versionNo,
                original_name: name || attachment.original_name
            });
        } else {
            await ApiClient.uploadAttachment(leadId, category, file);
        }
        written = true;
        if (!await refreshCurrentInquiryData(leadId, action)) {
            // The upload finished; the reader is looking at somebody else.
            await refreshNavigationCounts();
            return;
        }
        renderPanelContent('files');
        notify(attachment?.id
            ? fileActionText('File metadata updated.')
            : fileActionText('File uploaded.'));
        hideAttachmentForm();
    } catch (err) {
        // Uploaded but not redrawn is not a failed upload; sending somebody
        // back to attach the same file again is how duplicates appear.
        if (written) return InquiryPanelAction.savedButNotRefreshed(err);
        if (!InquiryPanelAction.isCurrent(action)) {
            return InquiryPanelAction.failedAfterMovingOn(err);
        }
        console.error('Attachment upload error:', err);
        alert(fileActionText('Error uploading file: {error}', {
            error: fileActionText(err?.message || 'Unknown error')
        }));
    } finally {
        InquiryPanelAction.release(action);
    }
};

window.downloadAttachment = async function(index) {
    const attachment = State.currentInquiry?.attachments?.[index];
    const leadId = State.currentInquiry?.id;
    if (!attachment || !leadId) return;

    try {
        const blob = await ApiClient.downloadAttachment(leadId, attachment.id);
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = attachment.original_name || 'attachment';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Attachment download error:', err);
        alert(fileActionText('Error downloading file: {error}', {
            error: fileActionText(err?.message || 'Unknown error')
        }));
    }
};

window.archiveAttachment = async function(index) {
    const attachment = State.currentInquiry?.attachments?.[index];
    const leadId = State.currentInquiry?.id;
    if (!attachment || !leadId) return;

    if (!confirm(fileActionText('Archive this file?'))) return;

    const action = InquiryPanelAction.begin();
    let archived = false;
    try {
        await ApiClient.archiveAttachment(leadId, attachment.id);
        archived = true;
        if (!await refreshCurrentInquiryData(leadId, action)) return;
        renderPanelContent('files');
    } catch (err) {
        if (archived) return InquiryPanelAction.archivedButNotRefreshed(err);
        if (!InquiryPanelAction.isCurrent(action)) {
            return InquiryPanelAction.failedAfterMovingOn(err);
        }
        console.error('Attachment archive error:', err);
        alert(fileActionText('Error archiving file: {error}', {
            error: fileActionText(err?.message || 'Unknown error')
        }));
    }
};
