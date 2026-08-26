/** Download saved trip plans in team-ready file formats. */
(function() {
    const FILE_LABELS = Object.freeze({
        xlsx: 'Excel itinerary',
        html: 'Web itinerary',
        ics: 'Calendar file',
        md: 'Markdown',
        csv: 'CSV',
    });

    function setStatus(message, tone = '') {
        const target = document.getElementById('trip-export-status');
        if (!target) return;
        target.textContent = message;
        target.className = `trip-export-status${tone ? ` ${tone}` : ''}`;
    }

    // These three are built from a model that has no member dimension, so a
    // team plan would download a file stating one colleague's journey as
    // everybody's. They are turned off rather than allowed to fail on click.
    const TEAM_UNSUPPORTED = Object.freeze(['xlsx', 'html', 'ics']);

    function refresh(plan) {
        const team = plan?.planning_mode === 'team';
        document.querySelectorAll('[data-trip-export-format]').forEach(button => {
            const format = button.getAttribute('data-trip-export-format');
            if (!TEAM_UNSUPPORTED.includes(format)) return;
            button.disabled = team;
            button.title = team
                ? I18n.t('Not available for a team trip yet. Use Markdown, CSV or the daily report.')
                : '';
        });
        const note = document.getElementById('trip-export-team-note');
        if (note) note.hidden = !team;
    }

    function setBusy(busy) {
        const panel = document.querySelector('.trip-export-panel');
        if (!panel) return;
        panel.setAttribute('aria-busy', String(busy));
        panel.querySelectorAll('[data-trip-export-format]').forEach(button => {
            button.disabled = busy;
        });
        if (!busy) refresh(State.currentTripPlan);
    }

    function canDownload() {
        if (!State.currentTripPlan?.id) {
            alert(I18n.t('Select a trip plan first'));
            return false;
        }
        if (window.TripBriefingDraft?.guard?.()) return false;
        if (window.TripVisitDraft?.guard?.()) return false;
        if (window.TripFreeStopDraft?.guardRouteAction?.()) return false;
        if (window.TripPlanningDraft?.get?.()?.dirty) {
            alert(I18n.t('Save the current route draft before exporting it.'));
            return false;
        }
        const summary = State.currentTripPlan.itinerary_summary || {};
        if (summary.stale === true || summary.valid === false) {
            alert(I18n.t('This route is out of date. Recalculate and save it before exporting.'));
            return false;
        }
        return true;
    }

    async function download(format) {
        if (!canDownload()) return;
        const fileLabel = I18n.t(FILE_LABELS[format] || format.toUpperCase());
        setBusy(true);
        setStatus(I18n.t('Generating {file}...', { file: fileLabel }), 'busy');
        try {
            const { blob, filename } = await ApiClient.exportTripPlan(State.currentTripPlan.id, format);
            downloadBlob(blob, filename);
            const message = I18n.t('Downloaded: {filename}', { filename });
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
            setBusy(false);
        }
    }

    window.TripExportActions = { download, setStatus, refresh };
    window.exportCurrentTripPlan = download;
})();
