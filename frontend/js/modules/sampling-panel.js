/** Sampling task panel renderer. */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

    function latestFollowUp(inquiry) {
        const item = inquiry.latest_follow_up || inquiry._lead?.latest_follow_up || {};
        const rawDate = inquiry.latest_follow_up_at_raw || item.occurred_at_raw || '';
        const date = inquiry.latest_follow_up_at
            || inquiry._lead?.latest_follow_up_at || item.created_at;
        const displayedDate = rawDate || (date ? formatDate(date) : tr('Not provided'));
        const content = inquiry.latest_follow_up_summary || inquiry._lead?.latest_follow_up_summary
            || item.content || item.summary;
        return `
            <div class="task-followup-summary">
                <div><span>${escapeHtml(tr('Latest follow-up'))}</span><strong>${escapeHtml(displayedDate)}</strong></div>
                <p>${escapeHtml(content || tr('No formal follow-up recorded'))}</p>
            </div>`;
    }

    function renderTask(task, index) {
        const archived = Boolean(task.archived_at);
        const manager = RoleCapabilities.canManageTaskRequests();
        const action = archived
            ? (manager ? `<button type="button" class="btn btn-sm btn-secondary" onclick="restoreSampleTask(${index})">${escapeHtml(tr('Restore'))}</button>` : '')
            : `<button type="button" class="btn btn-sm btn-secondary" onclick="editSampleTask(${index})">${escapeHtml(tr(manager ? 'Edit' : 'Update result'))}</button>
               ${manager ? `<button type="button" class="btn btn-sm btn-secondary" onclick="archiveSampleTask(${index})">${escapeHtml(tr('Archive'))}</button>` : ''}`;
        return `
            <article class="followup-item pre-sales-task-item ${archived ? 'is-archived' : ''}">
                <div class="followup-header">
                    <div class="followup-meta">
                        <span class="stage-badge">${escapeHtml(tr(task.status || 'Open'))}</span>
                        <span>${escapeHtml(task.assignee_name || tr('Unassigned'))}</span>
                        ${archived ? `<span>${escapeHtml(tr('Archived'))}</span>` : ''}
                    </div>
                    <div class="task-item-actions">${action}</div>
                </div>
                ${SamplingTaskDetails.render(task)}
            </article>`;
    }

    function render(inquiry) {
        const tasks = (inquiry.sample_tasks || [])
            .map((task, index) => ({ task, index }))
            .filter(item => RoleCapabilities.canManageTaskRequests() || !item.task.archived_at);
        const list = tasks.length
            ? tasks.map(item => renderTask(item.task, item.index)).join('')
            : `<div class="empty-state">${escapeHtml(tr('No pre-sales task yet.'))}</div>`;
        return `
            ${latestFollowUp(inquiry)}
            <div class="task-panel-heading">
                <h3>${escapeHtml(tr('Pre-sales tasks'))}</h3>
                <span>${escapeHtml(tr('{count} tasks', { count: tasks.length }))}</span>
                ${RoleCapabilities.canManageTaskRequests() ? `<button type="button" class="btn btn-primary btn-sm" onclick="showSampleTaskForm()">${escapeHtml(tr('+ New task'))}</button>` : ''}
            </div>
            <div>${list}</div>${SamplingTaskForm.render()}`;
    }

    window.SamplingPanel = { render };
})();
