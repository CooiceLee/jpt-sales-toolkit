/** Presentation helpers for governed JSON import and full-backup status. */
(function() {
    const tr = text => window.I18n?.t(text) || text;

    window.createFullBackup = async function() {
        const result = document.getElementById('backup-result');
        const button = document.getElementById('create-backup-btn');
        try {
            button.disabled = true;
            result.style.display = 'block';
            result.className = 'wizard-inline-result';
            result.textContent = tr('Creating full backup...');
            const report = await ApiClient.createFullBackup();
            result.className = 'wizard-inline-result success';
            result.innerHTML = `<strong>${escapeHtml(tr('Full backup created'))}</strong><br><code>${escapeHtml(report.backup_path || '')}</code>`;
            window.SpreadsheetImportProgress?.markBackupComplete?.();
        } catch (error) {
            result.className = 'wizard-inline-result error';
            result.textContent = `${tr('Backup failed')}: ${error.message || tr('Unknown error')}`;
        } finally {
            button.disabled = false;
        }
    };

    window.LegacyImportView = {
        renderImport(report) {
            const errors = report.errors || [];
            const skipped = Number(report.skipped_records || 0);
            const successful = Number(report.new_leads || 0) + Number(report.updated_leads || 0);
            const outcome = errors.length || skipped
                ? (successful > 0 ? 'partial' : 'failed')
                : 'success';
            const title = outcome === 'failed'
                ? tr('Import failed')
                : outcome === 'partial'
                    ? `${tr('Import Complete')} · ${tr('Skipped')}/${tr('Errors')}`
                    : tr('Import Complete');
            const borderColor = outcome === 'failed'
                ? 'var(--danger)'
                : outcome === 'partial'
                    ? 'var(--warning)'
                    : 'var(--success)';
            document.getElementById('json-import-result').innerHTML = `
                <div class="import-success import-${outcome}" data-import-outcome="${outcome}" style="border-left-color:${borderColor}"><h4>${title}</h4>
                    <div class="governance-kpis">
                        <span>${tr('Total')} <strong>${report.total_records || 0}</strong></span>
                        <span>${tr('Customers created')} <strong>${report.new_customers || 0}</strong></span>
                        <span>${tr('Customers updated')} <strong>${report.updated_customers || 0}</strong></span>
                        <span>${tr('Leads created')} <strong>${report.new_leads || 0}</strong></span>
                        <span>${tr('Leads updated')} <strong>${report.updated_leads || 0}</strong></span>
                        <span>${tr('Skipped')} <strong>${report.skipped_records || 0}</strong></span>
                    </div>${errors.length ? renderPreflightIssueList(tr('Errors'), errors) : ''}</div>`;
        },
        renderPreflight(report) {
            const issues = report.issues || [];
            const duplicates = report.duplicates || [];
            const total = Number(
                report.source_snapshot?.leads
                ?? (Number(report.permission?.allowed_leads || 0) + Number(report.permission?.skipped_leads || 0))
            );
            const skipped = Number(report.permission?.skipped_leads || 0);
            const blocked = Number(report.summary?.errors || 0) > 0 || skipped > 0;
            document.getElementById('json-preflight-result').innerHTML = `
                <div class="governance-report"><h4>${tr('JSON Preflight Result')}</h4>
                    <div class="governance-kpis">
                        <span>${tr('Total')} <strong>${total}</strong></span>
                        <span>${tr('Allowed leads')} <strong>${report.permission?.allowed_leads || 0}</strong></span>
                        <span>${tr('Skipped')} <strong>${skipped}</strong></span>
                        <span>${tr('Errors')} <strong>${report.summary?.errors || 0}</strong></span>
                        <span>${tr('Warnings')} <strong>${report.summary?.warnings || 0}</strong></span>
                        <span>${tr('Duplicates')} <strong>${report.summary?.duplicates || 0}</strong></span>
                    </div>
                    ${blocked ? `<div class="empty-state compact error-state">${escapeHtml(tr('Run preflight and resolve every blocking issue before import.'))}</div>` : ''}
                    ${issues.length ? renderPreflightIssueList(tr('Issues'), issues.map(item => `${item.severity.toUpperCase()} · ${item.entity}: ${item.message}`)) : `<div class="empty-state compact">${tr('No field or enum issues found')}</div>`}
                    ${duplicates.length ? renderPreflightIssueList(tr('Duplicate Signals'), duplicates.map(item => `${item.type} · ${item.name || item.email || item.customer_id}`)) : ''}
                </div>`;
        }
    };
})();
