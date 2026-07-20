(function() {
    const tr = text => window.I18n?.t(text) || text;
    const fileInput = () => document.getElementById('import-file');
    function selectedFile() {
        const file = fileInput()?.files?.[0];
        if (!file) alert(tr('Please select a file first'));
        return file;
    }
    function showError(error, target = 'import-result') {
        console.error('Import error:', error);
        const message = tr(error.message || 'Import failed');
        document.getElementById(target).innerHTML = `
            <div class="empty-state compact error-state">${escapeHtml(message)}</div>`;
        if (target === 'import-result') {
            const status = document.getElementById('import-commit-state');
            if (status) {
                status.textContent = message;
                status.classList.add('error-state');
            }
        }
    }
    function requireSpreadsheetLeader() {
        if (State.user?.role !== 'leader') throw new Error(tr('Controlled XLSX import is available to Leader accounts only.'));
    }
    async function runSpreadsheetPreflight(file) {
        let ticket = null;
        try {
            requireSpreadsheetLeader();
            if (!SpreadsheetImportState.isSpreadsheet(file)) throw new Error(tr('Only .xlsx workbooks are supported'));
            SpreadsheetImportState.useFile(file);
            document.getElementById('import-commit-state')?.classList.remove('error-state');
            document.getElementById('import-preflight-result').innerHTML = `<div class="loading-state">${tr('Running controlled preflight...')}</div>`;
            ticket = SpreadsheetImportProgress.begin('preflight', file);
            const report = await ApiClient.preflightSpreadsheetImport(file, SpreadsheetImportState.resolutions());
            if (!SpreadsheetImportProgress.isCurrent(ticket)) return;
            SpreadsheetImportState.setReport(file, report);
            SpreadsheetImportView.render(report);
            const setup = document.getElementById('import-setup-details');
            if (setup) setup.open = false;
        } catch (error) {
            if (!ticket || SpreadsheetImportProgress.isCurrent(ticket)) showError(error, 'import-preflight-result');
        } finally {
            if (ticket) SpreadsheetImportProgress.finish(ticket);
        }
    }
    window.preflightImportData = async function() {
        const file = selectedFile();
        if (file) return runSpreadsheetPreflight(file);
    };
    window.recheckSpreadsheetImport = async function() {
        const file = selectedFile();
        if (file && SpreadsheetImportState.isSpreadsheet(file)) return runSpreadsheetPreflight(file);
    };
    window.importData = async function() {
        const file = selectedFile();
        if (!file) return;
        let ticket = null;
        try {
            requireSpreadsheetLeader();
            if (!SpreadsheetImportState.canCommit(file)) throw new Error(tr('Run preflight and resolve every blocking issue before import.'));
            document.getElementById('import-commit-state')?.classList.remove('error-state');
            ticket = SpreadsheetImportProgress.begin('commit', file);
            const report = await ApiClient.commitSpreadsheetImport(
                file, SpreadsheetImportState.resolutions(), SpreadsheetImportState.sourceHash()
            );
            if (!SpreadsheetImportProgress.isCurrent(ticket)) return SpreadsheetImportProgress.markCommitUnconfirmed();
            renderSpreadsheetSuccess(report);
            fileInput().value = '';
            SpreadsheetImportState.useFile(null);
            document.getElementById('import-file-name').textContent = tr('No workbook selected');
            document.getElementById('import-setup-summary').textContent = tr('Import complete');
            SpreadsheetImportProgress.markCommitComplete();
            await refreshAllCounts().catch(error => {
                console.error('Post-import count refresh failed:', error);
                document.getElementById('import-result').insertAdjacentHTML('beforeend',
                    `<p class="error-state">${escapeHtml(tr('Import completed, but navigation counts could not be refreshed. Reopen JPT to load the latest counts.'))}</p>`);
            });
            return report;
        } catch (error) {
            if (ticket && !SpreadsheetImportProgress.isCurrent(ticket)) return SpreadsheetImportProgress.markCommitUnconfirmed();
            if (error.outcomeUnconfirmed) SpreadsheetImportProgress.markCommitUnconfirmed();
            if (error.report) {
                SpreadsheetImportState.setReport(file, error.report);
                SpreadsheetImportView.render(error.report);
            }
            showError(error);
        } finally {
            if (ticket) SpreadsheetImportProgress.finish(ticket);
        }
    };
    function renderSpreadsheetSuccess(report) {
        const summary = report.summary || report;
        const counts = Object.values(report.counts || {});
        const total = key => counts.reduce((sum, item) => sum + Number(item?.[key] || 0), 0);
        document.getElementById('import-result').innerHTML = `
            <div class="import-success">
                <h4>${tr('Spreadsheet Import Complete')}</h4>
                <div class="governance-kpis">
                    <span>${tr('Created')} <strong>${summary.created || total('created')}</strong></span>
                    <span>${tr('Updated')} <strong>${summary.updated || total('updated')}</strong></span>
                    <span>${tr('Archived')} <strong>${summary.archived || 0}</strong></span>
                    <span>${tr('Skipped')} <strong>${summary.skipped || 0}</strong></span>
                    <span>${tr('Warnings')} <strong>${summary.warnings || report.quality_issue_count || 0}</strong></span>
                </div>
                <small>${tr('Batch')} ${escapeHtml(report.batch_id || '')}</small>
            </div>`;
    }
    window.onImportFileChanged = function() {
        const file = fileInput()?.files?.[0];
        SpreadsheetImportProgress.selectionChanged();
        SpreadsheetImportState.useFile(file, true);
        SpreadsheetImportProgress.resetCommit();
        document.getElementById('import-commit-state')?.classList.remove('error-state');
        document.getElementById('import-file-name').textContent = file?.name || tr('No workbook selected');
        document.getElementById('import-setup-summary').textContent = file?.name || tr('No workbook selected');
        const setup = document.getElementById('import-setup-details');
        if (setup) setup.open = true;
        document.getElementById('import-preflight-result').innerHTML = `
            <div class="wizard-empty-state">${tr(file ? 'Workbook selected. Run preflight to review its contents.' : 'Select a workbook and run preflight to review rows, account mappings, customer matches and issues.')}</div>`;
        document.getElementById('import-result').innerHTML = '';
        if (file && State.user?.role !== 'leader') {
            showError(new Error(tr('Only a Leader can preflight or import XLSX files.')), 'import-preflight-result');
        }
    };
})();
