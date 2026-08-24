/** Loading, full-replacement saving and explicit geocoding for visit briefings. */
(function() {
    let requestEpoch = 0;
    let locationEpoch = 0;
    let candidates = [];
    const h = value => escapeHtml(value ?? '');

    function setEditorOpen(open) {
        const root = document.getElementById('trip-briefing-editor');
        if (!root) return null;
        root.hidden = !open;
        root.closest('.trip-schedule-workspace')?.classList.toggle('has-open-briefing', Boolean(open));
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
        if (TripBriefingDraft.getStopId() === stopId) return;
        if (TripBriefingDraft.guard()) return;
        const epoch = ++requestEpoch;
        locationEpoch += 1;
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
        locationEpoch += 1;
        candidates = [];
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
        try {
            setBusy(true);
            const data = await ApiClient.putTripBriefing(planId, stopId, payload);
            const stop = (State.currentTripPlan.stops || []).find(item => item.id === stopId);
            if (stop) {
                stop.row_version = data.stop_row_version ?? stop.row_version;
                stop.confirmation_status = data.confirmation_status || stop.confirmation_status;
            }
            TripBriefingDraft.markClean(data);
            TripBriefingForm.populate(data);
            renderCurrentTripPlan();
            window.TripScheduleView?.renderPlan?.(State.currentTripPlan);
            notify(I18n.t('Customer visit preparation saved.'));
        } catch (error) {
            console.error('Save trip briefing error:', error);
            if (error?.name === 'ConflictError') {
                TripBriefingDraft.setStatus(I18n.t('This preparation changed elsewhere. Your draft was not saved; refresh latest before editing again.'));
                alert(I18n.t('This preparation changed elsewhere. Your draft remains visible. Use Refresh latest to load the current saved version.'));
            } else await handleTripError(error, 'Save customer visit preparation');
        } finally { setBusy(false); }
    }

    async function refreshLatest() {
        const stopId = TripBriefingDraft.getStopId();
        if (!stopId) return;
        if (!TripBriefingDraft.confirmDiscard('Discard this draft and refresh the latest saved preparation?')) return;
        TripBriefingDraft.reset();
        await open(stopId);
    }

    function locationFields() {
        const values = {};
        document.querySelectorAll('[data-location-field]').forEach(input => {
            values[input.dataset.locationField] = input.value.trim();
        });
        return values;
    }

    async function searchLocation() {
        const fields = locationFields();
        if (![fields.address, fields.city, fields.postal_code, fields.country].some(Boolean)) {
            alert(I18n.t('Enter an address, city, postal code, or country first.')); return;
        }
        const epoch = ++locationEpoch;
        const planId = State.currentTripPlan?.id;
        const stopId = TripBriefingDraft.getStopId();
        const fingerprint = JSON.stringify(fields);
        const isCurrent = () => epoch === locationEpoch
            && planId === State.currentTripPlan?.id
            && stopId === TripBriefingDraft.getStopId()
            && fingerprint === JSON.stringify(locationFields());
        const status = document.getElementById('trip-briefing-location-status');
        const root = document.getElementById('trip-briefing-location-candidates');
        if (status) status.textContent = I18n.t('Searching location...');
        if (root) root.innerHTML = '';
        try {
            const result = await ApiClient.searchGeocode({
                address: fields.address, city: fields.city, postal_code: fields.postal_code, country: fields.country,
            }, 5);
            if (!isCurrent()) return;
            candidates = (result.candidates || []).filter(item => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lng)));
            if (root) root.innerHTML = candidates.map((item, index) => `<button type="button" class="btn btn-secondary btn-sm"
                onclick="TripBriefingActions.chooseLocation(${index})">${h(item.normalized_address || `${item.lat}, ${item.lng}`)}</button>`).join('');
            if (status) status.textContent = candidates.length
                ? I18n.t('Choose one result to confirm the custom visit coordinates.')
                : I18n.t('No matching location found. Refine the address or enter exact coordinates manually.');
        } catch (error) {
            if (!isCurrent()) return;
            console.error('Briefing location search error:', error);
            if (status) status.textContent = I18n.t('Location search failed. Check the network or enter coordinates manually.');
        }
    }

    function chooseLocation(index) {
        if (!candidates[index]) return;
        TripBriefingForm.setLocation(candidates[index]);
    }

    function cancelLocationSearch() {
        locationEpoch += 1;
        candidates = [];
        const root = document.getElementById('trip-briefing-location-candidates');
        if (root) root.innerHTML = '';
    }

    window.TripBriefingActions = Object.freeze({ open, close, save, refreshLatest,
        searchLocation, chooseLocation, cancelLocationSearch });
})();
