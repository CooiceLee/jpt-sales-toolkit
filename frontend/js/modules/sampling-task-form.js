/** Editable pre-sales task form; imported fields remain available for correction. */
(function () {
    'use strict';

    const tr = text => window.I18n?.t(text) || text;

    function options(values, selected) {
        return values.map(value =>
            `<option value="${escapeHtml(value)}" ${selected === value ? 'selected' : ''}>${escapeHtml(tr(value))}</option>`
        ).join('');
    }

    function input(id, label, type = 'text', extra = '') {
        return `<div class="form-group"><label class="form-label">${escapeHtml(tr(label))}</label>
            <input id="${id}" type="${type}" class="form-input" ${extra}></div>`;
    }

    function textarea(id, label, rows = 3) {
        return `<div class="form-group"><label class="form-label">${escapeHtml(tr(label))}</label>
            <textarea id="${id}" class="form-textarea" rows="${rows}"></textarea></div>`;
    }

    function render() {
        const managerClass = RoleCapabilities.canManageTaskRequests() ? '' : 'hidden';
        return `
            <div id="sample-task-form" class="sample-task-form hidden">
                <input type="hidden" id="sample-task-index" value="-1">
                <input type="hidden" id="sample-task-create-token" value="">
                <div class="task-detail-heading">${escapeHtml(tr('Task control'))}</div>
                <div class="form-row">
                    <div class="form-group"><label class="form-label">${escapeHtml(tr('Status'))}</label>
                        <select id="sample-task-status" class="form-select">${options(['Open', 'In Progress', 'Completed', 'Cancelled'], 'Open')}</select></div>
                    <div class="form-group ${managerClass}"><label class="form-label">${escapeHtml(tr('Pre-sales owner'))}</label>
                        <select id="sample-task-assignee" class="form-select"><option value="">${escapeHtml(tr('Unassigned'))}</option></select></div>
                </div>
                <div class="${managerClass}">
                    <div class="form-row">
                        ${input('sample-task-request-date', 'Request date', 'date')}
                        ${input('sample-task-due', 'Due date', 'date')}
                    </div>
                    ${textarea('sample-task-params', 'Request description', 4)}
                    <div class="form-row">
                        ${input('sample-task-decision-maker', 'Decision maker')}
                        ${input('sample-task-quantity', 'Quantity')}
                    </div>
                    ${input('sample-task-competitor', 'Competitor')}
                    ${textarea('sample-task-key-points', 'Key points')}
                    ${textarea('sample-task-concerns', 'Concerns')}
                </div>
                <div class="task-detail-heading">${escapeHtml(tr('Progress and result'))}</div>
                ${textarea('sample-task-progress', 'Current progress')}
                ${textarea('sample-task-next-action', 'Next action')}
                ${textarea('sample-task-result-summary', 'Result summary')}
                ${textarea('sample-task-notes', 'Supplemental notes')}
                <div class="form-row">
                    <div class="form-group"><label class="form-label">${escapeHtml(tr('Sample result'))}</label>
                        <select id="sample-task-result" class="form-select">${options(['Pending', 'Success', 'Failed', 'Cancelled'], 'Pending')}</select></div>
                    ${input('sample-task-confirmed', 'Confirmed date', 'date')}
                </div>
                ${input('sample-task-report', 'Report link')}
                <div class="sample-task-form-actions">
                    <button type="button" class="btn btn-secondary" onclick="hideSampleTaskForm()">${escapeHtml(tr('Cancel'))}</button>
                    <button type="button" class="btn btn-primary" id="sample-task-save" onclick="saveSampleTask()">${escapeHtml(tr('Save request'))}</button>
                </div>
            </div>`;
    }

    window.SamplingTaskForm = { render };
})();
