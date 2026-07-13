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

window.importData = async function() {
    const fileInput = document.getElementById('import-file');
    const file = fileInput?.files?.[0];

    if (!file) {
        alert('Please select a file to import');
        return;
    }

    try {
        const report = await ApiClient.importData(file);

        // Display import report
        const resultDiv = document.getElementById('import-result');
        resultDiv.innerHTML = `
            <div style="padding:16px;background:var(--success-light);border-radius:8px;margin-top:16px;">
                <h4 style="margin:0 0 12px 0;color:var(--success);">Import Complete</h4>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:14px;">
                    <div><strong>Total records:</strong> ${report.total_records}</div>
                    <div><strong>Source:</strong> ${report.source_user}</div>
                    <div><strong>New customers:</strong> ${report.new_customers}</div>
                    <div><strong>Updated customers:</strong> ${report.updated_customers}</div>
                    <div><strong>New leads:</strong> ${report.new_leads}</div>
                    <div><strong>Updated leads:</strong> ${report.updated_leads}</div>
                    <div><strong>Skipped:</strong> ${report.skipped_records}</div>
                    <div><strong>Errors:</strong> ${report.errors.length}</div>
                </div>
                ${report.errors.length > 0 ? `
                    <details style="margin-top:12px;">
                        <summary style="cursor:pointer;color:var(--danger);">View Errors</summary>
                        <ul style="margin:8px 0 0 0;padding-left:20px;font-size:13px;">
                            ${report.errors.map(e => `<li>${escapeHtml(e)}</li>`).join('')}
                        </ul>
                    </details>
                ` : ''}
            </div>
        `;

        // Clear file input
        fileInput.value = '';

        // Refresh dashboard if on dashboard
        const activeModule = document.querySelector('.module.active');
        if (activeModule?.id === 'module-dashboard') {
            loadDashboard();
        }
    } catch (err) {
        console.error('Import error:', err);
        const resultDiv = document.getElementById('import-result');
        resultDiv.innerHTML = `
            <div style="padding:16px;background:var(--danger-light);border-radius:8px;margin-top:16px;">
                <h4 style="margin:0 0 8px 0;color:var(--danger);">Import Failed</h4>
                <p style="margin:0;font-size:14px;">${escapeHtml(err.message || 'Unknown error')}</p>
            </div>
        `;
    }
};

window.preflightImportData = async function() {
    const fileInput = document.getElementById('import-file');
    const file = fileInput?.files?.[0];
    if (!file) {
        alert('Please select a file to preflight');
        return;
    }
    const resultDiv = document.getElementById('import-preflight-result');
    resultDiv.innerHTML = '<div class="loading-state">Running preflight...</div>';
    try {
        const report = await ApiClient.preflightImportData(file);
        const issues = report.issues || [];
        const duplicates = report.duplicates || [];
        resultDiv.innerHTML = `
            <div class="governance-report">
                <h4>Preflight Result</h4>
                <div class="governance-kpis">
                    <span>Allowed leads: <strong>${report.permission?.allowed_leads || 0}</strong></span>
                    <span>Skipped: <strong>${report.permission?.skipped_leads || 0}</strong></span>
                    <span>Errors: <strong>${report.summary?.errors || 0}</strong></span>
                    <span>Warnings: <strong>${report.summary?.warnings || 0}</strong></span>
                    <span>Duplicates: <strong>${report.summary?.duplicates || 0}</strong></span>
                </div>
                <div class="governance-kpis">
                    <span>New customers: <strong>${report.predicted?.new_customers || 0}</strong></span>
                    <span>Updated customers: <strong>${report.predicted?.updated_customers || 0}</strong></span>
                    <span>New leads: <strong>${report.predicted?.new_leads || 0}</strong></span>
                    <span>Updated leads: <strong>${report.predicted?.updated_leads || 0}</strong></span>
                </div>
                ${issues.length ? renderPreflightIssueList('Issues', issues.map(item => `${item.severity.toUpperCase()} · ${item.entity}: ${item.message}`)) : '<div class="empty-state compact">No field or enum issues found</div>'}
                ${duplicates.length ? renderPreflightIssueList('Duplicate Signals', duplicates.map(item => `${item.type} · ${item.name || item.email || item.customer_id}`)) : ''}
            </div>
        `;
    } catch (err) {
        console.error('Preflight error:', err);
        resultDiv.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(err.message || 'Preflight failed')}</div>`;
    }
};

