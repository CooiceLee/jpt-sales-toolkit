/** Sampling task panel renderer. */
(function() {
    function statusOptions(selected) {
        return ['Open', 'In Progress', 'Completed', 'Cancelled']
            .map(value => `<option value="${value}" ${selected === value ? 'selected' : ''}>${value}</option>`)
            .join('');
    }

    function resultOptions(selected) {
        return ['Pending', 'Success', 'Failed', 'Cancelled']
            .map(value => `<option value="${value}" ${selected === value ? 'selected' : ''}>${value}</option>`)
            .join('');
    }

    function renderTask(task, index) {
        const archived = Boolean(task.archived_at);
        const action = archived
            ? `<button type="button" class="btn btn-sm btn-secondary" onclick="restoreSampleTask(${index})">Restore</button>`
            : `<button type="button" class="btn btn-sm btn-secondary" onclick="editSampleTask(${index})">Edit</button>
               <button type="button" class="btn btn-sm btn-secondary" onclick="archiveSampleTask(${index})">Archive</button>`;
        return `
            <div class="followup-item" style="border-left:3px solid var(--info);${archived ? 'opacity:.6;' : ''}">
                <div class="followup-header">
                    <div class="followup-meta">
                        <span class="stage-badge">${escapeHtml(task.status || 'Open')}</span>
                        <span>${escapeHtml(task.assignee_name || 'Unassigned')}</span>
                        ${archived ? '<span>Archived</span>' : ''}
                    </div>
                    <div style="display:flex;gap:8px;">${action}</div>
                </div>
                <div class="followup-content">${escapeHtml(task.sample_params || 'No sample parameters')}</div>
                <div class="followup-meta" style="margin-top:8px;">
                    <span>Result: ${escapeHtml(task.sample_result || 'Pending')}</span>
                    <span>Due: ${task.due_date ? formatDate(task.due_date) : '-'}</span>
                    <span>Report: ${escapeHtml(task.report_link || '-')}</span>
                </div>
            </div>`;
    }

    function renderForm() {
        return `
            <div id="sample-task-form" class="hidden" style="margin-top:16px;padding:16px;background:var(--cream-100);border-radius:var(--radius-md);">
                <input type="hidden" id="sample-task-index" value="-1">
                <div class="form-row">
                    <div class="form-group"><label class="form-label">Status</label><select id="sample-task-status" class="form-select">${statusOptions('Open')}</select></div>
                    <div class="form-group"><label class="form-label">Pre-sales owner</label><select id="sample-task-assignee" class="form-select"><option value="">Unassigned</option></select></div>
                    <div class="form-group"><label class="form-label">Due date</label><input id="sample-task-due" type="date" class="form-input"></div>
                </div>
                <div class="form-group"><label class="form-label">Sample parameters / request</label><textarea id="sample-task-params" class="form-textarea" rows="4"></textarea></div>
                <div class="form-row">
                    <div class="form-group"><label class="form-label">Sample result</label><select id="sample-task-result" class="form-select">${resultOptions('Pending')}</select></div>
                    <div class="form-group"><label class="form-label">Report link</label><input id="sample-task-report" class="form-input"></div>
                    <div class="form-group"><label class="form-label">Confirmed date</label><input id="sample-task-confirmed" type="date" class="form-input"></div>
                </div>
                <div style="display:flex;gap:8px;justify-content:flex-end;">
                    <button type="button" class="btn btn-secondary" onclick="hideSampleTaskForm()">Cancel</button>
                    <button type="button" class="btn btn-primary" id="sample-task-save" onclick="saveSampleTask()">Save request</button>
                </div>
            </div>`;
    }

    function render(inquiry) {
        const tasks = inquiry.sample_tasks || [];
        const list = tasks.length
            ? tasks.map(renderTask).join('')
            : '<div class="empty-state">No sample request yet.</div>';
        return `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3>Sample requests</h3>
                <button type="button" class="btn btn-primary btn-sm" onclick="showSampleTaskForm()">+ New request</button>
            </div>
            <div>${list}</div>${renderForm()}`;
    }

    window.SamplingPanel = { render };
})();
