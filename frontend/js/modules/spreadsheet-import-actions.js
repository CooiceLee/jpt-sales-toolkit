(function() {
    const fileInput = () => document.getElementById('import-file');
    function selectedFile() {
        const file = fileInput()?.files?.[0];
        if (!file) alert('Please select a file first');
        return file;
    }
    function showError(error, target = 'import-result') {
        console.error('Import error:', error);
        document.getElementById(target).innerHTML = `
            <div class="empty-state compact error-state">${escapeHtml(error.message || 'Import failed')}</div>`;
    }

    function requireSpreadsheetLeader() {
        if (State.user?.role !== 'leader') {
            throw new Error('Controlled XLSX import is available to Leader accounts only.');
        }
    }

    async function runSpreadsheetPreflight(file) {
        requireSpreadsheetLeader();
        SpreadsheetImportState.useFile(file);
        const target = document.getElementById('import-preflight-result');
        target.innerHTML = '<div class="loading-state">Running controlled preflight...</div>';
        const report = await ApiClient.preflightSpreadsheetImport(
            file, SpreadsheetImportState.resolutions()
        );
        SpreadsheetImportState.setReport(file, report);
        SpreadsheetImportView.render(report);
    }

    window.preflightImportData = async function() {
        const file = selectedFile();
        if (!file) return;
        try {
            if (SpreadsheetImportState.isSpreadsheet(file)) {
                await runSpreadsheetPreflight(file);
            } else {
                document.getElementById('import-preflight-result').innerHTML = '<div class="loading-state">Running JSON preflight...</div>';
                LegacyImportView.renderPreflight(await ApiClient.preflightImportData(file));
            }
        } catch (error) {
            showError(error, 'import-preflight-result');
        }
    };

    window.recheckSpreadsheetImport = async function() {
        const file = selectedFile();
        if (!file || !SpreadsheetImportState.isSpreadsheet(file)) return;
        try {
            await runSpreadsheetPreflight(file);
        } catch (error) {
            showError(error, 'import-preflight-result');
        }
    };

    window.importData = async function() {
        const file = selectedFile();
        if (!file) return;
        try {
            if (!SpreadsheetImportState.isSpreadsheet(file)) {
                LegacyImportView.renderImport(await ApiClient.importData(file));
            } else {
                requireSpreadsheetLeader();
                if (!SpreadsheetImportState.canCommit(file)) {
                    throw new Error('Run preflight and resolve every blocking issue before import.');
                }
                const report = await ApiClient.commitSpreadsheetImport(
                    file,
                    SpreadsheetImportState.resolutions(),
                    SpreadsheetImportState.sourceHash()
                );
                renderSpreadsheetSuccess(report);
            }
            fileInput().value = '';
            SpreadsheetImportState.useFile(null);
            SpreadsheetImportView.syncCommitButton();
            if (document.querySelector('.module.active')?.id === 'module-dashboard') loadDashboard();
        } catch (error) {
            showError(error);
        }
    };

    function renderSpreadsheetSuccess(report) {
        const summary = report.summary || report;
        const counts = Object.values(report.counts || {});
        const total = key => counts.reduce((sum, item) => sum + Number(item?.[key] || 0), 0);
        document.getElementById('import-result').innerHTML = `
            <div class="import-success">
                <h4>Spreadsheet Import Complete</h4>
                <div class="governance-kpis">
                    <span>Created <strong>${summary.created || total('created')}</strong></span>
                    <span>Updated <strong>${summary.updated || total('updated')}</strong></span>
                    <span>Archived <strong>${summary.archived || 0}</strong></span>
                    <span>Skipped <strong>${summary.skipped || 0}</strong></span>
                    <span>Warnings <strong>${summary.warnings || report.quality_issue_count || 0}</strong></span>
                </div>
                <small>Batch ${escapeHtml(report.batch_id || '')}</small>
            </div>`;
    }

    window.onImportFileChanged = function() {
        const file = fileInput()?.files?.[0];
        SpreadsheetImportState.useFile(file);
        document.getElementById('import-preflight-result').innerHTML = '';
        document.getElementById('import-result').innerHTML = '';
        if (SpreadsheetImportState.isSpreadsheet(file) && State.user?.role !== 'leader') {
            showError(new Error('Only a Leader can preflight or import XLSX files.'), 'import-preflight-result');
        }
        SpreadsheetImportView.syncCommitButton();
    };
})();
