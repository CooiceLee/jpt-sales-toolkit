/** Independent workspaces for governed XLSX import, JSON exchange and governance. */
(function() {
    const tr = text => window.I18n?.t(text) || text;
    function defaultWorkspace() {
        return State.user?.role === 'leader' ? 'spreadsheet' : 'json';
    }
    window.showTransferWorkspace = function(target) {
        if (target !== 'json' && State.user?.role !== 'leader') target = 'json';
        document.querySelectorAll('.transfer-workspace').forEach(item => {
            item.classList.toggle('active', item.id === `transfer-${target}`);
        });
        document.querySelectorAll('[data-transfer-target]').forEach(button => {
            const active = button.dataset.transferTarget === target;
            button.classList.toggle('active', active);
            button.setAttribute('aria-selected', String(active));
        });
    };
    window.DataTransferWorkspace = {
        ensureAccessible() {
            const active = document.querySelector('.transfer-workspace.active')?.id?.replace('transfer-', '');
            const allowed = active === 'json' || State.user?.role === 'leader';
            window.showTransferWorkspace(active && allowed ? active : defaultWorkspace());
            window.SpreadsheetImportProgress?.sync?.();
        }
    };
    window.exportData = async function() {
        try {
            const { blob, filename } = await ApiClient.exportData();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            const result = document.getElementById('export-result');
            result.style.display = 'block';
            result.className = 'wizard-inline-result success';
            result.textContent = `✓ ${tr('Export successful!')} ${filename}`;
        } catch (error) {
            alert(`${tr('Export failed')}: ${error.message || tr('Unknown error')}`);
        }
    };
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
    function selectedJsonFile() {
        const file = document.getElementById('json-import-file')?.files?.[0];
        if (!file) alert(tr('Please select a JSON file first'));
        return file;
    }
    window.preflightJsonImport = async function() {
        const file = selectedJsonFile();
        if (!file) return;
        const target = document.getElementById('json-preflight-result');
        try {
            target.innerHTML = `<div class="loading-state">${tr('Running JSON preflight...')}</div>`;
            window.LegacyImportView.renderPreflight(await ApiClient.preflightImportData(file));
        } catch (error) {
            target.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(error.message || tr('Preflight failed'))}</div>`;
        }
    };
    window.importJsonData = async function() {
        const file = selectedJsonFile();
        if (!file) return;
        const target = document.getElementById('json-import-result');
        try {
            const report = await ApiClient.importData(file);
            window.LegacyImportView.renderImport(report);
            await refreshAllCounts();
            document.getElementById('json-import-file').value = '';
            return report;
        } catch (error) {
            target.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(error.message || tr('Import failed'))}</div>`;
        }
    };

    window.LegacyImportView = {
        renderImport(report) {
            const errors = report.errors || [];
            document.getElementById('json-import-result').innerHTML = `
                <div class="import-success"><h4>${tr('Import Complete')}</h4>
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
            document.getElementById('json-preflight-result').innerHTML = `
                <div class="governance-report"><h4>${tr('JSON Preflight Result')}</h4>
                    <div class="governance-kpis">
                        <span>${tr('Allowed leads')} <strong>${report.permission?.allowed_leads || 0}</strong></span>
                        <span>${tr('Errors')} <strong>${report.summary?.errors || 0}</strong></span>
                        <span>${tr('Warnings')} <strong>${report.summary?.warnings || 0}</strong></span>
                        <span>${tr('Duplicates')} <strong>${report.summary?.duplicates || 0}</strong></span>
                    </div>
                    ${issues.length ? renderPreflightIssueList(tr('Issues'), issues.map(item => `${item.severity.toUpperCase()} · ${item.entity}: ${item.message}`)) : `<div class="empty-state compact">${tr('No field or enum issues found')}</div>`}
                    ${duplicates.length ? renderPreflightIssueList(tr('Duplicate Signals'), duplicates.map(item => `${item.type} · ${item.name || item.email || item.customer_id}`)) : ''}
                </div>`;
        }
    };
})();
