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
        alert('No lead selected');
        return;
    }
    if (!Number.isInteger(versionNo) || versionNo < 1) {
        alert('Version must be a positive number');
        return;
    }
    if (!attachment && !file) {
        alert('Please choose a file');
        return;
    }

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
        notify(attachment?.id ? 'File metadata updated' : 'File uploaded');
        hideAttachmentForm();
    } catch (err) {
        console.error('Attachment upload error:', err);
        alert('Error uploading file: ' + (err.message || 'Unknown error'));
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
        alert('Error downloading file: ' + (err.message || 'Unknown error'));
    }
};

window.archiveAttachment = async function(index) {
    const attachment = State.currentInquiry?.attachments?.[index];
    const leadId = State.currentInquiry?.id;
    if (!attachment || !leadId) return;

    if (!confirm('Archive this file?')) return;

    try {
        await ApiClient.archiveAttachment(leadId, attachment.id);
        await refreshCurrentInquiryData(leadId);
        renderPanelContent('files');
    } catch (err) {
        console.error('Attachment archive error:', err);
        alert('Error archiving file: ' + (err.message || 'Unknown error'));
    }
};

