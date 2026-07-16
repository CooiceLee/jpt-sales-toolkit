// ===== Export/Import =====
window.exportData = async function() {
    try {
        // Export all user's leads
        const { blob, filename } = await ApiClient.exportData();

        // Create download link
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        // Show success message
        const result = document.getElementById('export-result');
        result.style.display = 'block';
        setText('export-result', `✓ Export successful! File: ${filename}`);
    } catch (err) {
        console.error('Export error:', err);
        alert('Export failed: ' + (err.message || 'Unknown error'));
    }
};

window.createFullBackup = async function() {
    const tr = text => window.I18n?.t(text) || text;
    const result = document.getElementById('backup-result');
    const button = document.getElementById('create-backup-btn');
    try {
        button.disabled = true;
        result.style.display = 'block';
        result.textContent = tr('Creating full backup...');
        const report = await ApiClient.createFullBackup();
        result.innerHTML = `<strong>${escapeHtml(tr('Full backup created'))}</strong><br><code>${escapeHtml(report.backup_path || '')}</code>`;
    } catch (err) {
        console.error('Backup error:', err);
        result.textContent = `${tr('Backup failed')}: ${err.message || tr('Unknown error')}`;
    } finally {
        button.disabled = false;
    }
};

window.LegacyImportView = {
    renderImport(report) {
        const errors = report.errors || [];
        document.getElementById('import-result').innerHTML = `
            <div class="import-success">
                <h4>Import Complete</h4>
                <div class="governance-kpis">
                    <span>Total <strong>${report.total_records || 0}</strong></span>
                    <span>Customers created <strong>${report.new_customers || 0}</strong></span>
                    <span>Customers updated <strong>${report.updated_customers || 0}</strong></span>
                    <span>Leads created <strong>${report.new_leads || 0}</strong></span>
                    <span>Leads updated <strong>${report.updated_leads || 0}</strong></span>
                    <span>Skipped <strong>${report.skipped_records || 0}</strong></span>
                </div>
                ${errors.length ? renderPreflightIssueList('Errors', errors) : ''}
            </div>`;
    },
    renderPreflight(report) {
        const issues = report.issues || [];
        const duplicates = report.duplicates || [];
        document.getElementById('import-preflight-result').innerHTML = `
            <div class="governance-report">
                <h4>JSON Preflight Result</h4>
                <div class="governance-kpis">
                    <span>Allowed leads <strong>${report.permission?.allowed_leads || 0}</strong></span>
                    <span>Errors <strong>${report.summary?.errors || 0}</strong></span>
                    <span>Warnings <strong>${report.summary?.warnings || 0}</strong></span>
                    <span>Duplicates <strong>${report.summary?.duplicates || 0}</strong></span>
                </div>
                ${issues.length ? renderPreflightIssueList('Issues', issues.map(item => `${item.severity.toUpperCase()} · ${item.entity}: ${item.message}`)) : '<div class="empty-state compact">No field or enum issues found</div>'}
                ${duplicates.length ? renderPreflightIssueList('Duplicate Signals', duplicates.map(item => `${item.type} · ${item.name || item.email || item.customer_id}`)) : ''}
            </div>`;
    }
};
