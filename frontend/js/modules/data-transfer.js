/** Independent workspaces for governed XLSX import, JSON exchange and governance. */
(function() {
    const tr = text => window.I18n?.t(text) || text;
    let jsonPreflightApproval = null;
    let jsonPreflightRequest = 0;
    let jsonImportBusy = false;

    function jsonFileSignature(file) {
        return file ? `${file.name}:${file.size}:${file.lastModified}` : '';
    }
    function jsonImportButton() {
        return document.getElementById('json-import-btn')
            || document.getElementById('json-import-commit-btn')
            || document.querySelector?.('#transfer-json button[onclick="importJsonData()"]')
            || null;
    }
    function jsonPreflightAllows(file) {
        return Boolean(
            file
            && jsonPreflightApproval?.approved
            && jsonPreflightApproval.file === file
            && jsonPreflightApproval.signature === jsonFileSignature(file)
        );
    }
    function syncJsonImportGate() {
        const file = document.getElementById('json-import-file')?.files?.[0];
        const button = jsonImportButton();
        if (!button) return;
        button.disabled = jsonImportBusy || !jsonPreflightAllows(file);
        button.setAttribute('aria-disabled', String(button.disabled));
        button.title = jsonPreflightAllows(file)
            ? tr('Ready to import')
            : tr('Run preflight and resolve every blocking issue before import.');
    }
    function resetJsonPreflight(clearResults = false) {
        jsonPreflightApproval = null;
        jsonPreflightRequest += 1;
        if (clearResults) {
            const preflight = document.getElementById('json-preflight-result');
            const imported = document.getElementById('json-import-result');
            if (preflight) preflight.innerHTML = '';
            if (imported) imported.innerHTML = '';
        }
        syncJsonImportGate();
    }
    function bindJsonImportGate() {
        const input = document.getElementById('json-import-file');
        if (!input || input.dataset.jsonPreflightGateBound === 'true') {
            syncJsonImportGate();
            return;
        }
        input.dataset.jsonPreflightGateBound = 'true';
        input.addEventListener('change', () => resetJsonPreflight(true));
        syncJsonImportGate();
    }

    function defaultWorkspace() {
        if (State.user?.role === 'leader') return 'spreadsheet';
        return State.user?.role === 'tech' ? 'tech' : 'json';
    }
    function workspaceAllowed(target) {
        const role = State.user?.role;
        if (role === 'leader') return ['spreadsheet', 'json', 'tech', 'governance', 'merge'].includes(target);
        if (role === 'tech') return target === 'tech';
        return target === 'json';
    }
    window.showTransferWorkspace = function(target) {
        if (!workspaceAllowed(target)) target = defaultWorkspace();
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
            window.showTransferWorkspace(active && workspaceAllowed(active) ? active : defaultWorkspace());
            window.SpreadsheetImportProgress?.sync?.();
            window.JsonExport?.ensureRecipients?.();
            window.TechTaskPackageView?.ensureRole?.();
            bindJsonImportGate();
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
        const signature = jsonFileSignature(file);
        const request = ++jsonPreflightRequest;
        jsonPreflightApproval = null;
        syncJsonImportGate();
        try {
            target.innerHTML = `<div class="loading-state">${tr('Running JSON preflight...')}</div>`;
            const report = await ApiClient.preflightImportData(file);
            const currentFile = document.getElementById('json-import-file')?.files?.[0];
            if (
                request !== jsonPreflightRequest
                || currentFile !== file
                || jsonFileSignature(currentFile) !== signature
            ) return;
            const errorCount = Number(report.summary?.errors || 0);
            const skippedCount = Number(report.permission?.skipped_leads || 0);
            jsonPreflightApproval = {
                file,
                signature,
                approved: errorCount === 0 && skippedCount === 0,
            };
            window.LegacyImportView.renderPreflight(report);
        } catch (error) {
            if (request !== jsonPreflightRequest) return;
            target.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(error.message || tr('Preflight failed'))}</div>`;
        } finally {
            syncJsonImportGate();
        }
    };
    window.importJsonData = async function() {
        const file = selectedJsonFile();
        if (!file) return;
        const target = document.getElementById('json-import-result');
        if (!jsonPreflightAllows(file)) {
            target.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(tr('Run preflight and resolve every blocking issue before import.'))}</div>`;
            syncJsonImportGate();
            return;
        }
        jsonImportBusy = true;
        jsonPreflightApproval = null;
        syncJsonImportGate();
        try {
            const report = await ApiClient.importData(file);
            window.LegacyImportView.renderImport(report);
            try {
                await refreshAllCounts();
            } catch (refreshError) {
                console.error('JSON import count refresh failed:', refreshError);
            }
            document.getElementById('json-import-file').value = '';
            return report;
        } catch (error) {
            target.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(error.message || tr('Import failed'))}</div>`;
        } finally {
            jsonImportBusy = false;
            syncJsonImportGate();
        }
    };

    if (document.readyState === 'loading' && document.addEventListener) {
        document.addEventListener('DOMContentLoaded', bindJsonImportGate, { once: true });
    } else {
        bindJsonImportGate();
    }
})();
