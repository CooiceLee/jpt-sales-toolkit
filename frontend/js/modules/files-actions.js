function fileActionText(text, params = {}) {
    return window.I18n?.t ? I18n.t(text, params) : Object.entries(params)
        .reduce((value, [key, item]) => value.replace(`{${key}}`, item), text);
}

window.saveAttachment = async function() {
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

    const saveButton = document.getElementById('attachment-save-btn');
    if (saveButton?.disabled) return;
    if (saveButton) saveButton.disabled = true;
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
        await refreshCurrentInquiryData(leadId);
        renderPanelContent('files');
        notify(attachment?.id
            ? fileActionText('File metadata updated.')
            : fileActionText('File uploaded.'));
        hideAttachmentForm();
    } catch (err) {
        console.error('Attachment upload error:', err);
        alert(fileActionText('Error uploading file: {error}', {
            error: fileActionText(err?.message || 'Unknown error')
        }));
    } finally {
        const currentButton = document.getElementById('attachment-save-btn');
        if (currentButton) currentButton.disabled = false;
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

    try {
        await ApiClient.archiveAttachment(leadId, attachment.id);
        await refreshCurrentInquiryData(leadId);
        renderPanelContent('files');
    } catch (err) {
        console.error('Attachment archive error:', err);
        alert(fileActionText('Error archiving file: {error}', {
            error: fileActionText(err?.message || 'Unknown error')
        }));
    }
};
