/** Guarded offline task package exchange between Leader and Tech terminals. */
(function () {
    'use strict';
    const tr = text => window.I18n?.t(text) || text;
    const states = {
        assignment: { input: 'tech-assignment-file', button: 'tech-assignment-import', result: 'tech-assignment-result', approval: null, request: 0, busy: false },
        result: { input: 'tech-result-file', button: 'tech-result-import', result: 'tech-result-result', approval: null, request: 0, busy: false },
    };

    function signature(file) {
        return file ? `${file.name}:${file.size}:${file.lastModified}` : '';
    }

    function approved(kind) {
        const state = states[kind];
        const file = document.getElementById(state.input)?.files?.[0];
        return Boolean(file && state.approval?.file === file && state.approval.signature === signature(file));
    }

    function syncGate(kind) {
        const state = states[kind];
        const button = document.getElementById(state.button);
        if (!button) return;
        button.disabled = state.busy || !approved(kind);
        button.setAttribute('aria-disabled', String(button.disabled));
        button.title = approved(kind) ? tr('Ready to import') : tr('Run a clean preflight for this file before import');
    }

    function reset(kind, clear = true) {
        const state = states[kind];
        state.approval = null;
        state.request += 1;
        if (clear) document.getElementById(state.result).innerHTML = '';
        syncGate(kind);
    }

    function clean(report) {
        const count = window.TechTaskPackageView.count;
        return report?.can_import === true
            && ['errors', 'skipped', 'conflicts'].every(name => count(report, name) === 0);
    }

    function selected(kind) {
        const state = states[kind];
        const file = document.getElementById(state.input)?.files?.[0];
        if (!file) alert(tr('Please select a task package first'));
        return file;
    }

    function methods(kind) {
        return kind === 'assignment'
            ? [ApiClient.preflightTechTaskAssignments, ApiClient.importTechTaskAssignments]
            : [ApiClient.preflightTechTaskResults, ApiClient.importTechTaskResults];
    }

    window.onTechTaskPackageFileChanged = kind => reset(kind);
    window.preflightTechTaskPackage = async function (kind) {
        const file = selected(kind);
        if (!file) return;
        const state = states[kind];
        const request = ++state.request;
        const fileSignature = signature(file);
        state.approval = null;
        syncGate(kind);
        window.TechTaskPackageView.renderMessage(state.result, 'Running task package preflight...');
        try {
            const report = await methods(kind)[0](file);
            const current = document.getElementById(state.input)?.files?.[0];
            if (request !== state.request || current !== file || signature(current) !== fileSignature) return;
            if (clean(report)) state.approval = { file, signature: fileSignature };
            window.TechTaskPackageView.renderReport(state.result, report, 'Task package preflight');
        } catch (error) {
            if (request === state.request) window.TechTaskPackageView.renderMessage(state.result, error.message || 'Preflight failed', 'error');
        } finally {
            syncGate(kind);
        }
    };

    window.importTechTaskPackage = async function (kind) {
        const file = selected(kind);
        const state = states[kind];
        if (!file || !approved(kind)) return syncGate(kind);
        state.busy = true;
        state.approval = null;
        syncGate(kind);
        try {
            const report = await methods(kind)[1](file);
            window.TechTaskPackageView.renderReport(state.result, report, 'Task package import complete');
            document.getElementById(state.input).value = '';
            try { await refreshAllCounts(); } catch (error) { console.error('Task package count refresh failed:', error); }
        } catch (error) {
            window.TechTaskPackageView.renderMessage(state.result, error.message || 'Import failed', 'error');
        } finally {
            state.busy = false;
            syncGate(kind);
        }
    };

    async function exportPackage(apiMethod, targetId, recipient = null) {
        try {
            const result = await apiMethod(recipient);
            downloadBlob(result.blob, result.filename);
            window.TechTaskPackageView.renderMessage(targetId, 'Task package downloaded', 'success');
        } catch (error) {
            window.TechTaskPackageView.renderMessage(targetId, error.message || 'Export failed', 'error');
        }
    }

    window.exportTechTaskAssignments = function () {
        const recipient = document.getElementById('tech-task-recipient')?.value;
        if (!recipient) return alert(tr('Please select a technical member'));
        return exportPackage(ApiClient.exportTechTaskAssignments, 'tech-assignment-export-result', recipient);
    };
    window.exportTechTaskResults = () => exportPackage(ApiClient.exportTechTaskResults, 'tech-result-export-result');
    window.TechTaskPackages = { syncGates: () => Object.keys(states).forEach(syncGate) };
})();
