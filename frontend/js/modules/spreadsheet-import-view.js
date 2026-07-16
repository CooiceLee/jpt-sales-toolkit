/** Rendering for spreadsheet preflight, mappings, exclusions, and commit state. */
(function() {
    const safe = value => escapeHtml(String(value ?? ''));
    const tr = text => window.I18n?.t(text) || text;
    const asList = (value, keyName) => Array.isArray(value) ? value : Object.entries(value || {}).map(
        ([key, item]) => item && typeof item === 'object' ? { [keyName]: key, ...item } : { [keyName]: key }
    );

    function candidateOptions(items, selected, type) {
        const first = type === 'customer'
            ? `<option value="__CREATE__">${tr('Create new customer')}</option>`
            : `<option value="">${tr('Select account')}</option>`;
        const choices = items || [];
        const selectedAvailable = choices.some(item =>
            (item.user_id || item.customer_id || item.id || '') === selected
        );
        const fallback = selected && selected !== '__CREATE__' && !selectedAvailable
            ? `<option value="${safe(selected)}" selected>Matched ${safe(type)} · ${safe(selected)}</option>`
            : '';
        return first + fallback + choices.map(item => {
            const id = item.user_id || item.customer_id || item.id || '';
            const label = item.username
                ? `${item.display_name || item.username} · ${item.username} · ${item.role || ''}`
                : `${item.display_name || item.name || id}${item.match_type ? ` · ${item.match_type}` : ''}`;
            return `<option value="${safe(id)}" ${id === selected ? 'selected' : ''}>${safe(label)}</option>`;
        }).join('');
    }

    function memberRows(report) {
        const defaults = report.member_candidates || [];
        return asList(report.member_mappings || report.unresolved_members, 'source_name').map(item => {
            const name = item.source_name || item.token || '';
            const selected = SpreadsheetImportState.resolutions().member_mappings[name]
                || item.user_id || '';
            return `<label class="import-resolution-row">
                <span><strong>${safe(name)}</strong><small>${safe(item.purpose || '')} · ${safe(tr(item.status || item.matched_by || 'unresolved'))}</small></span>
                <select class="form-input" data-member-key="${safe(name)}">${candidateOptions(item.candidates || defaults, selected, 'member')}</select>
            </label>`;
        }).join('');
    }

    function customerRows(report) {
        return asList(report.customer_mappings || report.customer_matches, 'external_key').map(item => {
            const key = item.external_key || item.customer_key || '';
            const selected = SpreadsheetImportState.resolutions().customer_mappings[key]
                || item.customer_id || '__CREATE__';
            return `<label class="import-resolution-row">
                <span><strong>${safe(item.display_name || key)}</strong><small>${safe(tr(item.status || item.match_type || 'new customer'))}</small></span>
                <select class="form-input" data-customer-key="${safe(key)}">${candidateOptions(item.candidates, selected, 'customer')}</select>
            </label>`;
        }).join('');
    }

    function issueRows(report) {
        const excluded = new Set(SpreadsheetImportState.resolutions().excluded_records);
        return (report.issues || []).map(item => {
            const key = item.source_record_key || item.source_ref?.record_key || item.external_key || '';
            const canExclude = ['error', 'blocker'].includes(item.severity)
                && item.entity_type !== 'member' && key;
            return `<li class="import-issue import-issue-${safe(item.severity || 'info')}">
                <span><strong>${safe((item.severity || 'info').toUpperCase())}</strong> · ${safe(item.code || item.issue_code)} · ${safe(item.message)}</span>
                ${canExclude ? `<label><input type="checkbox" data-exclude-key="${safe(key)}" ${excluded.has(key) ? 'checked' : ''}> ${tr('Exclude record')}</label>` : ''}
            </li>`;
        }).join('');
    }

    function render(report) {
        const summary = report.summary || {};
        const entityTotal = summary.total || summary.total_entities || Object.values(
            summary.entities || summary.entity_counts || {}
        )
            .reduce((total, count) => total + Number(count || 0), 0);
        const sourceRows = report.canonical_summary?.total_source_rows
            || summary.total_rows || summary.source_rows || 0;
        const members = memberRows(report);
        const customers = customerRows(report);
        document.getElementById('import-preflight-result').innerHTML = `
            <div class="governance-report spreadsheet-preflight">
                <div class="import-report-head"><h4>${tr('Spreadsheet Preflight')}</h4><span>${safe(report.format)} · ${safe(report.dataset_id)}</span></div>
                <div class="governance-kpis">
                    <span>${tr('Source rows')} <strong>${sourceRows}</strong></span>
                    <span>${tr('Entities')} <strong>${entityTotal}</strong></span>
                    <span>${tr('Errors')} <strong>${summary.error_count ?? summary.errors ?? summary.blockers ?? 0}</strong></span>
                    <span>${tr('Warnings')} <strong>${summary.warning_count ?? summary.warnings ?? 0}</strong></span>
                </div>
                ${members ? `<section class="import-resolution"><h5>${tr('Member account mapping')}</h5>${members}</section>` : ''}
                ${customers ? `<section class="import-resolution"><h5>${tr('Customer matching')}</h5>${customers}</section>` : ''}
                <section class="import-resolution"><h5>${tr('Issues and exclusions')}</h5><ul class="import-issue-list">${issueRows(report) || `<li>${tr('No issues found')}</li>`}</ul></section>
                <button type="button" class="btn btn-secondary" onclick="recheckSpreadsheetImport()">${tr('Apply corrections & recheck')}</button>
                <span class="import-commit-state">${tr(report.can_commit ? 'Ready to import' : 'Resolve or exclude all blockers before import')}</span>
            </div>`;
        bindResolutionInputs();
        syncCommitButton();
    }

    function bindResolutionInputs() {
        document.querySelectorAll('[data-member-key]').forEach(input => input.addEventListener('change', event => {
            SpreadsheetImportState.setMember(event.target.dataset.memberKey, event.target.value);
            syncCommitButton();
        }));
        document.querySelectorAll('[data-customer-key]').forEach(input => input.addEventListener('change', event => {
            SpreadsheetImportState.setCustomer(event.target.dataset.customerKey, event.target.value);
            syncCommitButton();
        }));
        document.querySelectorAll('[data-exclude-key]').forEach(input => input.addEventListener('change', event => {
            SpreadsheetImportState.toggleExcluded(event.target.dataset.excludeKey, event.target.checked);
            syncCommitButton();
        }));
    }

    function syncCommitButton() {
        const file = document.getElementById('import-file')?.files?.[0];
        const button = document.getElementById('import-commit-btn');
        if (button) button.disabled = SpreadsheetImportState.isSpreadsheet(file) && !SpreadsheetImportState.canCommit(file);
    }

    window.SpreadsheetImportView = { render, syncCommitButton };
})();
