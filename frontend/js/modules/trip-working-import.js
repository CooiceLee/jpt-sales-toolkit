/** Review and submit the field workbook returned from a customer visit. */
(function() {
    const tr = (text, params = {}) => Object.entries(params).reduce(
        (value, [key, item]) => value.replace(`{${key}}`, item),
        window.I18n?.t(text) || text);
    const esc = value => window.escapeHtml?.(value ?? '') || String(value ?? '');
    // Each request is numbered. Choosing another file while one is in flight
    // makes the answer to the old one stale: the database still gets the file
    // that was submitted, but showing its report beside a different filename
    // would read as "this file has been imported".
    const state = { file: null, report: null, resolutions: {}, busy: false, turn: 0 };

    function input() { return document.getElementById('trip-working-import-file'); }
    function result() { return document.getElementById('trip-working-import-result'); }
    function sameFile() {
        const file = input()?.files?.[0] || null;
        return Boolean(file && state.file === file);
    }

    function syncButtons() {
        const preflight = document.getElementById('trip-working-preflight-btn');
        const commit = document.getElementById('trip-working-commit-btn');
        const chooser = input();
        // The file cannot be swapped under a request that is already running.
        if (chooser) chooser.disabled = state.busy;
        if (preflight) preflight.disabled = state.busy || !chooser?.files?.[0];
        const conflicts = state.report?.conflicts || [];
        const resolved = conflicts.every(item => state.resolutions[item.token]?.[item.field]);
        // A mixture of choices that cannot be saved is refused here, not by
        // the server after the reader has pressed the button.
        const unsaveable = (state.report?.rows || []).some(
            row => TripWorkingImportView.unsaveable(row, state.resolutions));
        if (commit) commit.disabled = state.busy || !sameFile() || !state.report
            || unsaveable
            || !state.report.preview_digest || state.report.status === 'completed'
            || Boolean(state.report.issues?.length) || !resolved;
    }

    function render(report, message = '') {
        const target = result();
        if (!target) return;
        const issues = (report?.issues || []).map(item =>
            `<li>${esc(tr(item.message))}</li>`).join('');
        const rows = (report?.rows || [])
            .map(row => TripWorkingImportView.visitBlock(row, state.resolutions))
            .join('');
        const status = TripWorkingImportText.status(report, tr);
        target.innerHTML = `${message ? `<div class="empty-state compact">${esc(message)}</div>` : ''}
            ${report ? `<div class="trip-working-report"><p><strong>${esc(report.plan_title || '')}</strong> · ${esc(status)}</p>
            ${issues ? `<div class="empty-state compact error-state"><ul>${issues}</ul></div>` : ''}
            ${rows || `<p>${esc(tr('No customer visits were found in this workbook.'))}</p>`}</div>` : ''}`;
        target.querySelectorAll('[data-trip-working-token]').forEach(select =>
            select.addEventListener('change', event => {
                const { tripWorkingToken: token, tripWorkingField: field } = event.target.dataset;
                state.resolutions[token] = {
                    ...(state.resolutions[token] || {}), [field]: event.target.value,
                };
                syncButtons();
            }));
        syncButtons();
    }

    function reset(file = null) {
        state.file = file;
        state.report = null;
        state.resolutions = {};
    }

    async function preflight() {
        const file = input()?.files?.[0];
        if (!file) return;
        reset(file);
        const turn = ++state.turn;
        state.busy = true;
        render(null, tr('Reading the workbook...'));
        syncButtons();
        try {
            const report = await ApiClient.preflightTripWorking(file);
            if (turn !== state.turn) return;
            state.report = report;
            render(report);
        } catch (error) {
            if (turn !== state.turn) return;
            const report = error.details?.report;
            state.report = report || null;
            render(report, tr(error.message) || tr('The workbook could not be read.'));
        } finally {
            if (turn === state.turn) { state.busy = false; syncButtons(); }
        }
    }

    async function commit() {
        if (!state.report || !sameFile()) return;
        const turn = ++state.turn;
        // The number the plan on screen arrived under - not the newest, which
        // may already belong to a plan the reader has clicked and is waiting
        // for. Borrowing that one would let this redraw answer in its place.
        const planTurn = TripPlanIdentity.accepted();
        state.busy = true; syncButtons();
        try {
            const report = await ApiClient.importTripWorking(
                state.file, state.report.source_hash,
                state.report.preview_digest, state.resolutions);
            if (turn !== state.turn) return;
            state.report = report;
            state.resolutions = {};
            render(report, await TripWorkingImportRefresh.after(report, tr, planTurn));
        } catch (error) {
            if (turn !== state.turn) return;
            const report = error.details?.report;
            if (report) {
                // The plan moved, so the choices were about something else.
                if (report.resolutions_cleared) state.resolutions = {};
                state.report = report;
                render(report, tr(error.message));
            } else {
                render(state.report, tr(error.message) || tr('The import did not run.'));
            }
        } finally {
            if (turn === state.turn) { state.busy = false; syncButtons(); }
        }
    }

    function bind() {
        const file = input();
        if (!file || file.dataset.tripWorkingBound === 'true') return;
        file.dataset.tripWorkingBound = 'true';
        file.addEventListener('change', () => {
            // Another file is another question: the answer to the last one is
            // no longer about what is on screen.
            state.turn += 1;
            state.busy = false;
            reset();
            render(null);
            syncButtons();
        });
        document.getElementById('trip-working-preflight-btn')?.addEventListener('click', preflight);
        document.getElementById('trip-working-commit-btn')?.addEventListener('click', commit);
        syncButtons();
    }

    window.TripWorkingImport = { preflight, commit, render };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once: true });
    else bind();
})();
