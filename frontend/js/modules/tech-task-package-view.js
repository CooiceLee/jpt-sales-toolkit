/** Role-aware presentation for the isolated Leader/Tech task exchange. */
(function () {
    'use strict';
    const tr = text => window.I18n?.t(text) || text;
    let recipientsLoaded = false;

    function count(report, name) {
        const summary = report?.summary || {};
        const direct = report?.[name];
        const aliases = {
            total: [summary.total, report?.total_records, report?.task_count],
            errors: [summary.errors, report?.error_count, report?.errors?.length],
            warnings: [summary.warnings, report?.warning_count, report?.warnings?.length],
            skipped: [summary.skipped, report?.skipped_records, report?.permission?.skipped_tasks],
            conflicts: [summary.conflicts, report?.conflict_count, report?.conflicts?.length],
        };
        const candidates = [
            typeof direct === 'number' ? direct : undefined,
            Array.isArray(direct) ? direct.length : undefined,
            ...(aliases[name] || []),
        ];
        const value = candidates.find(item => item !== undefined && item !== null) ?? 0;
        return Number(value) || 0;
    }

    function issueText(issue) {
        if (typeof issue === 'string') return tr(issue);
        return tr(issue?.message || issue?.detail || issue?.code || JSON.stringify(issue));
    }

    function issueList(report) {
        const asArray = value => Array.isArray(value) ? value : [];
        const issues = [
            ...asArray(report?.issues), ...asArray(report?.errors),
            ...asArray(report?.conflicts), ...asArray(report?.warnings),
        ];
        if (!issues.length) return '';
        return `<details class="governance-details"><summary>${escapeHtml(tr('Review details'))}</summary>` +
            `<ul>${issues.slice(0, 50).map(item => `<li>${escapeHtml(issueText(item))}</li>`).join('')}</ul></details>`;
    }

    function renderReport(targetId, report, title) {
        const target = document.getElementById(targetId);
        if (!target) return;
        target.innerHTML = `<div class="governance-report"><h4>${escapeHtml(tr(title))}</h4>` +
            `<div class="governance-kpis">` +
            `<span>${tr('Total')} <strong>${count(report, 'total')}</strong></span>` +
            `<span>${tr('Errors')} <strong>${count(report, 'errors')}</strong></span>` +
            `<span>${tr('Warnings')} <strong>${count(report, 'warnings')}</strong></span>` +
            `<span>${tr('Skipped')} <strong>${count(report, 'skipped')}</strong></span>` +
            `<span>${tr('Conflicts')} <strong>${count(report, 'conflicts')}</strong></span></div>` +
            issueList(report) + `</div>`;
    }

    function renderMessage(targetId, message, status = '') {
        const target = document.getElementById(targetId);
        if (!target) return;
        target.innerHTML = `<div class="wizard-inline-result ${status}">${escapeHtml(tr(message))}</div>`;
    }

    async function ensureRecipients() {
        const select = document.getElementById('tech-task-recipient');
        if (!select || State.user?.role !== 'leader' || recipientsLoaded) return;
        try {
            const users = await ApiClient.listUsers('tech');
            const active = (users || []).filter(user => user.is_active !== false);
            select.innerHTML = `<option value="">${escapeHtml(tr('Select technical member'))}</option>` +
                active.map(user => `<option value="${escapeHtml(user.id)}">${escapeHtml(user.display_name)}</option>`).join('');
            recipientsLoaded = true;
        } catch (_error) {
            select.innerHTML = `<option value="">${escapeHtml(tr('Unable to load technical members'))}</option>`;
        }
    }

    function ensureRole() {
        const role = State.user?.role;
        document.querySelectorAll('[data-tech-task-role]').forEach(item => {
            item.hidden = item.dataset.techTaskRole !== role;
        });
        if (role === 'leader') ensureRecipients();
        window.TechTaskPackages?.syncGates?.();
    }

    window.TechTaskPackageView = { count, renderReport, renderMessage, ensureRole };
})();
