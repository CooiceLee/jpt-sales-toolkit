/** Controls Excel import buttons, status text and four-step progress. */
(function() {
    const tr = text => window.I18n?.t(text) || text;
    let backupComplete = false;
    let commitComplete = false;
    let commitUnconfirmed = false;
    let busyAction = null;
    let requestNonce = 0;
    let selectionEpoch = 0;
    let activeTicket = null;

    function fileSignature(file) {
        return file ? `${file.name}:${file.size}:${file.lastModified}` : '';
    }

    function sync() {
        const input = document.getElementById('import-file');
        const file = input?.files?.[0];
        const hasFile = SpreadsheetImportState.isSpreadsheet(file);
        const hasReport = SpreadsheetImportState.hasReport();
        const dirty = SpreadsheetImportState.isDirty();
        const canCommit = !commitUnconfirmed && hasFile && SpreadsheetImportState.canCommit(file);
        const report = SpreadsheetImportState.report();
        const blockers = Number(
            report?.summary?.error_count ?? report?.summary?.errors
            ?? report?.summary?.blockers ?? 0
        );
        const preflight = document.getElementById('import-preflight-btn');
        const recheck = document.getElementById('import-recheck-btn');
        const commit = document.getElementById('import-commit-btn');
        const busy = Boolean(busyAction);
        const pickerDisabled = busy || commitUnconfirmed || State.user?.role !== 'leader';
        const picker = document.querySelector('.workbook-picker[for="import-file"]');
        if (input) input.disabled = pickerDisabled;
        if (picker) {
            picker.setAttribute('aria-disabled', String(pickerDisabled));
            picker.style.pointerEvents = pickerDisabled ? 'none' : '';
            picker.style.opacity = pickerDisabled ? '.55' : '';
        }
        if (preflight) preflight.disabled = busy || !hasFile || State.user?.role !== 'leader';
        if (recheck) recheck.disabled = busy || !hasFile || !hasReport;
        const status = busyAction === 'preflight' ? 'Running controlled preflight...'
            : busy ? 'Importing workbook...'
            : commitUnconfirmed ? 'Import outcome unconfirmed — reopen JPT and verify the navigation counts and target records before any retry.'
            : commitComplete ? 'Import complete'
            : (!hasFile || !hasReport) ? 'Run preflight before import'
            : dirty ? 'Apply corrections & recheck'
            : canCommit ? 'Ready to import'
            : `${blockers} ${tr('blocking issues remain — resolve mappings or exclude invalid records, then recheck.')}`;
        if (commit) {
            commit.disabled = busy || !canCommit;
            commit.textContent = tr(busyAction === 'commit' ? 'Importing...' : 'Import & Merge');
            commit.title = status;
            commit.setAttribute('aria-disabled', String(commit.disabled));
        }
        const statusElement = document.getElementById('import-commit-state');
        if (statusElement) statusElement.textContent = tr(status);
        syncWizard(hasFile, hasReport, dirty, canCommit);
    }

    function syncWizard(hasFile, hasReport, dirty, canCommit) {
        const steps = Object.fromEntries([...document.querySelectorAll('[data-wizard-step]')]
            .map(item => [item.dataset.wizardStep, item]));
        Object.values(steps).forEach(item => item.classList.remove('active', 'complete'));
        if (backupComplete) steps.backup?.classList.add('complete');
        if (commitComplete) {
            ['file', 'preflight', 'commit'].forEach(key => steps[key]?.classList.add('complete'));
            return;
        }
        steps.file?.classList.add(hasFile ? 'complete' : 'active');
        if (hasFile) steps.preflight?.classList.add(hasReport && !dirty ? 'complete' : 'active');
        if (canCommit) steps.commit?.classList.add('active');
    }

    window.addEventListener('language:changed', sync);
    window.SpreadsheetImportProgress = {
        sync,
        markBackupComplete() { backupComplete = true; sync(); },
        resetCommit() { commitComplete = false; sync(); },
        markCommitComplete() { commitComplete = true; commitUnconfirmed = false; sync(); },
        markCommitUnconfirmed() { commitComplete = false; commitUnconfirmed = true; sync(); },
        selectionChanged() { selectionEpoch += 1; },
        begin(action, file) {
            busyAction = action;
            const ticket = { nonce: ++requestNonce, selectionEpoch, file, fileSignature: fileSignature(file) };
            activeTicket = ticket;
            sync();
            return ticket;
        },
        isCurrent(ticket) {
            const file = document.getElementById('import-file')?.files?.[0];
            return ticket?.nonce === activeTicket?.nonce && ticket.selectionEpoch === selectionEpoch
                && ticket.file === file && ticket.fileSignature === fileSignature(file);
        },
        finish(ticket) {
            if (ticket?.nonce === activeTicket?.nonce) { busyAction = null; activeTicket = null; }
            sync();
        },
        isBusy: () => Boolean(busyAction),
        isCommitUnconfirmed: () => commitUnconfirmed
    };
})();
