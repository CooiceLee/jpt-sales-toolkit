/** Loading, full-replacement saving and explicit geocoding for visit briefings. */
(function() {
    let requestEpoch = 0;
    const h = value => escapeHtml(value ?? '');

    function setEditorOpen(open) {
        const root = TripBriefingReveal.editor();
        if (!root) return null;
        if (open) TripBriefingReveal.show(root);
        else root.hidden = true;
        root.closest('.trip-briefing-workspace')?.classList.toggle('has-open-briefing', Boolean(open));
        return root;
    }

    function setEditorLoading(message) {
        const root = setEditorOpen(true);
        if (!root) return;
        root.innerHTML = `<div class="panel-loading">${h(I18n.t(message))}</div>`;
    }

    function setBusy(busy) {
        ['trip-briefing-save', 'trip-briefing-refresh', 'trip-briefing-location-search']
            .forEach(id => { const el = document.getElementById(id); if (el) el.disabled = busy; });
        document.getElementById('trip-briefing-editor')?.setAttribute('aria-busy', String(Boolean(busy)));
    }

    async function open(stopId) {
        const planId = State.currentTripPlan?.id;
        if (!planId || !stopId) return;
        if (TripBriefingDraft.getStopId() === stopId) return setEditorOpen(true);
        if (TripBriefingDraft.guard()) return;
        const epoch = ++requestEpoch;
        window.TripBriefingGeocode?.cancelLocationSearch?.();
        setEditorLoading('Loading customer visit preparation...');
        try {
            const data = await ApiClient.getTripBriefing(planId, stopId);
            if (epoch !== requestEpoch || State.currentTripPlan?.id !== planId) return;
            TripBriefingDraft.load(stopId, data);
            TripBriefingForm.populate(data);
        } catch (error) {
            if (epoch !== requestEpoch) return;
            console.error('Load trip briefing error:', error);
            setEditorLoading('Unable to load customer visit preparation.');
        }
    }

    function close(options = {}) {
        if (!options.force && !TripBriefingDraft.confirmDiscard()) return false;
        requestEpoch += 1;
        window.TripBriefingGeocode?.cancelLocationSearch?.();
        TripBriefingDraft.reset();
        const root = setEditorOpen(false);
        if (root) root.innerHTML = '';
        return true;
    }

    async function save() {
        const planId = State.currentTripPlan?.id;
        const stopId = TripBriefingDraft.getStopId();
        if (!planId || !stopId) return;
        let payload;
        try { payload = TripBriefingForm.payload(); }
        catch (error) { alert(error.message); return; }
        // A list nobody chose still means "whoever is travelling". A list the
        // reader chose keeps its people, even when it happens to be everybody.
        if (TripBriefingDraft.staysInherited(payload.participants)) {
            payload.participants = [];
        }
        // An address search started before this save is still out, and its
        // answer draws buttons that were not there to be held. Choosing one
        // rebuilt the form - unfrozen - over values this save had already
        // taken, so the new address was neither sent nor kept. The search is
        // dropped here; after a failed save the reader can search again.
        window.TripBriefingGeocode?.cancelLocationSearch?.();
        // This save owns this editor until it finishes: the fields it took its
        // values from are held, and the identity it belongs to is carried so
        // the tail cannot close an editor the reader has since opened.
        const session = TripBriefingSession.begin({ planId, stopId, epoch: requestEpoch });
        const mine = () => TripBriefingSession.isCurrent(session, requestEpoch);
        try {
            setBusy(true);
            const data = await ApiClient.putTripBriefing(planId, stopId, payload);
            if (!mine()) {
                // Written, and the reader has moved on. Saying nothing would
                // read as lost work; touching the screen would take the plan
                // they are on now away from them.
                notify(I18n.t('The earlier visit preparation was saved. Reopen that visit to see it.'));
                return;
            }
            TripBriefingDraft.markClean(data);
            close({ force: true });
            // Written and read back are two different things to be wrong
            // about. Who attends and where the visit is both decide the route,
            // so the server marks the itinerary out of date when either
            // changes; the plan is read back under the number the screen
            // already had, so this cannot finish in place of a plan the reader
            // asked for meanwhile. If that read fails, the write still stands -
            // saying nothing left the reader looking at the old summary with no
            // idea whether their work was saved.
            try {
                await TripPlanRefresh.reread(planId, { token: session.token });
                // Two facts, and the reader needs both: the preparation is
                // saved, and - when the place or the attendees decided the
                // route - the route it was calculated from is no longer the
                // one on file. Saying only the first reads as "all done".
                const stale = window.TripRouteState?.derive?.()?.serverStale;
                notify(I18n.t(stale
                    ? 'Visit preparation saved. The route changed with it and needs recalculating.'
                    : 'Customer visit preparation saved.'));
            } catch (refreshError) {
                console.error('Refresh after saving a visit briefing failed:', refreshError);
                notify(I18n.t('The visit preparation was saved, but the page could not be refreshed. Reopen this visit to see the latest - do not save again.'));
            }
        } catch (error) {
            console.error('Save trip briefing error:', error);
            if (!mine()) return;
            if (error?.name === 'ConflictError') {
                TripBriefingDraft.setStatus(I18n.t('This preparation changed elsewhere. Your draft was not saved; refresh latest before editing again.'));
                alert(I18n.t('This preparation changed elsewhere. Your draft remains visible. Use Refresh latest to load the current saved version.'));
            } else await handleTripError(error, 'Save customer visit preparation');
        } finally {
            TripBriefingSession.release(session, requestEpoch);
            if (mine()) setBusy(false);
        }
    }

    async function refreshLatest() {
        const stopId = TripBriefingDraft.getStopId();
        if (!stopId) return;
        if (!TripBriefingDraft.confirmDiscard('Discard this draft and refresh the latest saved preparation?')) return;
        TripBriefingDraft.reset();
        await open(stopId);
    }

    window.TripBriefingActions = Object.freeze({ open, close, save, refreshLatest,
        searchLocation: (...args) => TripBriefingGeocode.searchLocation(...args),
        chooseLocation: (...args) => TripBriefingGeocode.chooseLocation(...args),
        cancelLocationSearch: (...args) => TripBriefingGeocode.cancelLocationSearch(...args) });
})();
