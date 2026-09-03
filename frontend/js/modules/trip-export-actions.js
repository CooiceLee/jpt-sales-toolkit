/** Download saved trip plans in team-ready file formats. */
(function() {
    function setStatus(message, tone = '') {
        const target = document.getElementById('trip-export-status');
        if (!target) return;
        target.textContent = message;
        target.className = `trip-export-status${tone ? ` ${tone}` : ''}`;
    }

    function updateButtons(plan) {
        // A button that cannot produce a file says so before it is pressed,
        // and says why. Refusing after the click leaves the reader guessing
        // which of five conditions they are in.
        const reason = TripExportNaming.blockedReason(plan);
        document.querySelectorAll('[data-trip-export-format]').forEach(button => {
            button.disabled = Boolean(reason);
            button.title = reason ? I18n.t(reason) : '';
        });
        return reason;
    }

    function refresh(plan) {
        // Called when another plan is opened: the last download belonged to
        // whichever plan was open then, so its result goes with it rather than
        // standing over a plan it was not made from.
        setStatus(I18n.t(updateButtons(plan) || 'Choose a file to download.'));
    }

    function setBusy(busy, plan) {
        const panel = document.querySelector('.trip-export-panel');
        if (!panel) return;
        panel.setAttribute('aria-busy', String(busy));
        panel.querySelectorAll('[data-trip-export-format]').forEach(button => {
            button.disabled = busy;
        });
        // Finishing a download leaves its own result standing.
        if (!busy) updateButtons(plan);
    }

    function canDownload(plan) {
        if (!plan?.id) {
            alert(I18n.t('Select a trip plan first'));
            return false;
        }
        if (window.TripBriefingDraft?.guard?.()) return false;
        if (window.TripVisitDraft?.guard?.()) return false;
        if (window.TripFreeStopDraft?.guardRouteAction?.()) return false;
        const reason = TripExportNaming.blockedReason(plan);
        if (reason) {
            alert(I18n.t(reason));
            return false;
        }
        return true;
    }

    async function download(format, variant = '') {
        // The plan is fixed here, at the click. Waiting for a file is long
        // enough to open another plan in, and a file that arrives named after
        // whatever is on screen by then is the wrong file sent to a customer.
        const plan = State.currentTripPlan;
        if (!canDownload(plan)) return;
        const document_ = TripExportNaming.document(format, variant);
        const fileLabel = I18n.t(document_.label);
        setBusy(true, plan);
        setStatus(I18n.t('Generating {file} for {plan}...', {
            file: fileLabel, plan: plan.title || '',
        }), 'busy');
        try {
            const { blob, filename } = await ApiClient.exportTripPlan(
                plan.id, format, variant);
            const name = TripExportNaming.filename(plan, format, variant, filename);
            downloadBlob(blob, name);
            const message = I18n.t('Downloaded: {filename}', { filename: name });
            setStatus(message, 'success');
            window.notify?.(message);
        } catch (error) {
            console.error('Export trip plan error:', error);
            const message = I18n.t('Download failed: {error}', {
                error: I18n.t(error.message || 'Unknown error'),
            });
            setStatus(message, 'error');
            window.notify?.(message);
        } finally {
            setBusy(false, State.currentTripPlan);
        }
    }

    window.TripExportActions = { download, setStatus, refresh };
    window.exportCurrentTripPlan = download;
})();
