// ===== Files Tab =====
function renderFilesTab(inq) {
    const attachments = inq.attachments || [];
    const categories = [
        { value: 'email_original', label: 'Original Email' },
        { value: 'quotation', label: 'Quotation' },
        { value: 'report', label: 'Report' },
        { value: 'test_result', label: 'Test Result' },
        { value: 'screenshot', label: 'Screenshot' },
        { value: 'other', label: 'Other' }
    ];

    const list = attachments.map((attachment, i) => `
        <div class="followup-item" style="border-left:3px solid var(--info);">
            <div class="followup-header">
                <div class="followup-meta">
                    <span class="followup-method">${escapeHtml(attachment.original_name || 'Attachment')}</span>
                    <span class="stage-badge">${escapeHtml(attachment.category || 'other')}</span>
                </div>
                <div style="display:flex;gap:8px;">
                    <button type="button" class="btn btn-sm btn-secondary" onclick="editAttachment(${i})">Edit</button>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="downloadAttachment(${i})">Download</button>
                    <button type="button" class="btn btn-sm btn-secondary" onclick="archiveAttachment(${i})">Archive</button>
                </div>
            </div>
            <div class="followup-dates">
                <span>${formatFileSize(attachment.size_bytes)}</span>
                <span>v${attachment.version_no || 1}</span>
                <span>${attachment.uploader_name ? `By ${escapeHtml(attachment.uploader_name)}` : ''}</span>
                <span>${formatDate(attachment.uploaded_at)}</span>
            </div>
        </div>
    `).join('');

    return `
        ${list || '<div class="empty-state">No files uploaded yet.</div>'}
        <button type="button" class="btn btn-secondary mt-4" onclick="showAttachmentForm()">+ Upload File</button>
        <div id="attachment-form" class="hidden" style="margin-top:16px;padding:16px;background:var(--cream-100);border-radius:var(--radius-md);">
            <input type="hidden" id="attachment-index" value="-1">
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Category</label>
                    <select id="attachment-category" class="form-select">
                        ${categories.map(item => `<option value="${item.value}">${item.label}</option>`).join('')}
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Version</label>
                    <input type="number" id="attachment-version" class="form-input" min="1" value="1">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Display Name</label>
                <input type="text" id="attachment-name" class="form-input" placeholder="Keep blank to use file name">
            </div>
            <div class="form-row" id="attachment-file-row">
                <div class="form-group">
                    <label class="form-label">File</label>
                    <input type="file" id="attachment-file" class="form-input">
                </div>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px;">
                <button type="button" id="attachment-save-btn" class="btn btn-primary" onclick="saveAttachment()">Upload</button>
                <button type="button" class="btn btn-secondary" onclick="hideAttachmentForm()">Cancel</button>
            </div>
        </div>
    `;
}

