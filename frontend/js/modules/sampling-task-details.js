/** Read-only, lossless display of every supported Excel pre-sales task field. */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const display = value => value === undefined || value === null || value === ''
        ? tr('Not provided')
        : String(value);

    function dateValue(value, rawValue = '') {
        if (value) return formatDate(value);
        return display(rawValue);
    }

    function row(label, value, wide = false) {
        return `
            <div class="task-detail-row ${wide ? 'task-detail-wide' : ''}">
                <span class="task-detail-label">${escapeHtml(tr(label))}</span>
                <span class="task-detail-value">${escapeHtml(display(value))}</span>
            </div>`;
    }

    function render(task) {
        return `
            <div class="task-detail-section">
                <div class="task-detail-heading">${escapeHtml(tr('Request and scope'))}</div>
                <div class="task-detail-grid">
                    ${row('Request description', task.request_description, true)}
                    ${row('Request date', dateValue(task.request_date))}
                    ${row('Request date (source)', task.request_date_raw)}
                    ${row('Due date', dateValue(task.due_date))}
                    ${row('Due date (source)', task.due_date_raw)}
                    ${row('Decision maker', task.customer_decision_maker)}
                    ${row('Quantity', task.quantity_text)}
                    ${row('Competitor', task.competitor)}
                    ${row('Key points', task.key_points, true)}
                    ${row('Concerns', task.concerns, true)}
                </div>
            </div>
            <div class="task-detail-section">
                <div class="task-detail-heading">${escapeHtml(tr('Progress and result'))}</div>
                <div class="task-detail-grid">
                    ${row('Current progress', task.progress_text, true)}
                    ${row('Next action', task.next_action, true)}
                    ${row('Result summary', task.result_summary, true)}
                    ${row('Supplemental notes', task.supplemental_notes, true)}
                    ${row('Sample result', tr(task.sample_result || 'Pending'))}
                    ${row('Confirmed date', dateValue(task.confirmed_date))}
                    ${row('Report link', task.report_link, true)}
                </div>
            </div>`;
    }

    window.SamplingTaskDetails = { render };
})();
