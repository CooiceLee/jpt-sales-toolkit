// ===== After-sales Tab =====
function renderAftersalesTab(inq) {
    const issues = inq.after_sales || [];

    const statusColors = {
        'Open': 'var(--danger)',
        'In Progress': 'var(--warning)',
        'Resolved': 'var(--success)',
        'Closed': 'var(--ink-500)'
    };

    const list = issues.map((issue, i) => {
        const color = statusColors[issue.status] || 'var(--ink-500)';
        return `
            <div class="followup-item" style="border-left: 3px solid ${color};">
                <div class="followup-header">
                    <div class="followup-meta">
                        <span class="followup-method">${issue.issue_type || 'Issue'}</span>
                        <span class="stage-badge" style="background:${color};color:white;">${issue.status || 'Open'}</span>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button type="button" class="btn btn-sm btn-secondary" onclick="editAfterSales(${i})">Edit</button>
                        <button type="button" class="btn btn-sm btn-secondary" onclick="archiveAfterSales(${i})">Archive</button>
                    </div>
                </div>
                <div class="followup-dates">
                    <span>Date: ${formatDate(issue.issue_date)}</span>
                    <span>${issue.technician ? `Tech: ${issue.technician}` : ''}</span>
                </div>
                <div class="followup-content">${issue.issue_description || ''}</div>
                ${issue.solution ? `<div class="followup-feedback"><label>Solution</label>${issue.solution}</div>` : ''}
            </div>
        `;
    }).join('');

    return `
        ${list || '<div class="empty-state">No after-sales issues recorded.</div>'}
        <button type="button" class="btn btn-secondary mt-4" onclick="showAfterSalesForm()">+ Log Issue</button>
        <div id="aftersales-form" class="hidden" style="margin-top:16px;padding:16px;background:var(--cream-100);border-radius:var(--radius-md);">
            <input type="hidden" id="as-index" value="-1">
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Date</label>
                    <input type="datetime-local" id="as-date" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">Type</label>
                    <select id="as-type" class="form-select">
                        <option value="Technical">Technical</option>
                        <option value="Quality">Quality</option>
                        <option value="Delivery">Delivery</option>
                        <option value="Other">Other</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Description</label>
                <textarea id="as-description" class="form-textarea" rows="2"></textarea>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Technician</label>
                    <input type="text" id="as-tech" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">Status</label>
                    <select id="as-status" class="form-select">
                        <option value="Open">Open</option>
                        <option value="In Progress">In Progress</option>
                        <option value="Resolved">Resolved</option>
                        <option value="Closed">Closed</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Solution</label>
                <textarea id="as-solution" class="form-textarea" rows="2"></textarea>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px;">
                <button type="button" id="as-save-btn" class="btn btn-primary" onclick="saveAfterSales()">Save</button>
                <button type="button" class="btn btn-secondary" onclick="hideAfterSalesForm()">Cancel</button>
            </div>
        </div>
    `;
}

