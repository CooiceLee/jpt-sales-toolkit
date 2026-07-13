// ===== Follow-ups Tab =====
function renderFollowupsTab(inq) {
    const followUps = inq.follow_ups || [];

    const statusColors = {
        pending: 'var(--warning)',
        responded: 'var(--info)',
        completed: 'var(--success)',
        scheduled: '#8B5CF6'
    };

    const list = followUps.map((fu, i) => {
        const color = statusColors[fu.status] || 'var(--ink-500)';
        return `
            <div class="followup-item" style="border-left: 3px solid ${color};">
                <div class="followup-header">
                    <div class="followup-meta">
                        <span class="followup-method">${fu.method || 'Follow-up'}</span>
                        <span class="stage-badge" style="background:${color};color:white;">${fu.status || 'pending'}</span>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button type="button" class="btn btn-sm btn-secondary" onclick="editFollowUp(${i})">Edit</button>
                        <button type="button" class="btn btn-sm btn-secondary" onclick="archiveFollowUp(${i})">Archive</button>
                    </div>
                </div>
                <div class="followup-dates">
                    <span>Sent: ${formatDate(fu.date)}</span>
                    <span>${fu.response_date ? `Response: ${formatDate(fu.response_date)}` : ''}</span>
                </div>
                <div class="followup-content">${fu.content || ''}</div>
                ${fu.customer_feedback ? `<div class="followup-feedback"><label>Customer Feedback</label>${fu.customer_feedback}</div>` : ''}
                ${fu.next_action ? `<div class="followup-next"><strong>Next:</strong> ${fu.next_action} ${fu.next_action_date ? `(${formatDate(fu.next_action_date)})` : ''}</div>` : ''}
            </div>
        `;
    }).join('');

    return `
        ${list || '<div class="empty-state">No follow-ups recorded yet.</div>'}
        <button type="button" class="btn btn-secondary mt-4" onclick="showFollowUpForm()">+ Add Follow-up</button>
        <div id="followup-form" class="hidden" style="margin-top:16px;padding:16px;background:var(--cream-100);border-radius:var(--radius-md);">
            <input type="hidden" id="fu-index" value="-1">
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Date</label>
                    <input type="datetime-local" id="fu-date" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">Method</label>
                    <select id="fu-method" class="form-select">
                        <option value="Email">Email</option>
                        <option value="Phone">Phone</option>
                        <option value="Meeting">Meeting</option>
                        <option value="Video Call">Video Call</option>
                        <option value="WhatsApp">WhatsApp</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Content</label>
                <textarea id="fu-content" class="form-textarea" rows="2"></textarea>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Status</label>
                    <select id="fu-status" class="form-select">
                        <option value="pending">Pending</option>
                        <option value="responded">Responded</option>
                        <option value="completed">Completed</option>
                        <option value="scheduled">Scheduled</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Response Date</label>
                    <input type="datetime-local" id="fu-response" class="form-input">
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Customer Feedback</label>
                <textarea id="fu-feedback" class="form-textarea" rows="2"></textarea>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label class="form-label">Next Action</label>
                    <input type="text" id="fu-next" class="form-input">
                </div>
                <div class="form-group">
                    <label class="form-label">Next Action Date</label>
                    <input type="date" id="fu-next-date" class="form-input">
                </div>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px;">
                <button type="button" id="fu-save-btn" class="btn btn-primary" onclick="saveFollowUp()">Save</button>
                <button type="button" class="btn btn-secondary" onclick="hideFollowUpForm()">Cancel</button>
            </div>
        </div>
    `;
}

