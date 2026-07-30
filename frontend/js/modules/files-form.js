window.showAttachmentForm = function() {
    document.getElementById('attachment-form')?.classList.remove('hidden');
    const indexInput = document.getElementById('attachment-index');
    if (indexInput) indexInput.value = '-1';
    const category = document.getElementById('attachment-category');
    if (category) category.value = 'other';
    const version = document.getElementById('attachment-version');
    if (version) version.value = '1';
    const name = document.getElementById('attachment-name');
    if (name) name.value = '';
    const fileInput = document.getElementById('attachment-file');
    if (fileInput) {
        fileInput.value = '';
        fileInput.disabled = false;
    }
    document.getElementById('attachment-file-row')?.classList.remove('hidden');
    const saveBtn = document.getElementById('attachment-save-btn');
    if (saveBtn) saveBtn.textContent = 'Upload';
};

window.hideAttachmentForm = function() {
    document.getElementById('attachment-form')?.classList.add('hidden');
    window.PanelDirtyState?.reset?.();
};

window.editAttachment = function(index) {
    const attachment = State.currentInquiry?.attachments?.[index];
    if (!attachment) return;

    document.getElementById('attachment-form')?.classList.remove('hidden');
    document.getElementById('attachment-index').value = index;
    document.getElementById('attachment-category').value = attachment.category || 'other';
    document.getElementById('attachment-version').value = attachment.version_no || 1;
    document.getElementById('attachment-name').value = attachment.original_name || '';

    const fileInput = document.getElementById('attachment-file');
    if (fileInput) {
        fileInput.value = '';
        fileInput.disabled = true;
    }
    document.getElementById('attachment-file-row')?.classList.add('hidden');
    const saveBtn = document.getElementById('attachment-save-btn');
    if (saveBtn) saveBtn.textContent = 'Update';
    document.getElementById('attachment-form')?.scrollIntoView({ block: 'nearest' });
};
