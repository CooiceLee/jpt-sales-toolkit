/** Editor state for non-customer itinerary stops. */
(function() {
    const CATEGORIES = Object.freeze(['rest', 'hotel', 'airport', 'transit', 'meal', 'other']);
    const WAYPOINT_CATEGORIES = Object.freeze(['airport', 'transit']);
    let candidates = [];
    let contextVersion = 0;
    let chosenIndex = -1;
    const el = id => document.getElementById(id);
    const value = id => String(el(id)?.value ?? '').trim();
    const set = (id, next) => { if (el(id)) el(id).value = next ?? ''; };

    function status(message = '', kind = '') {
        const root = el('trip-free-stop-geocode-status');
        if (!root) return;
        root.className = `trip-free-stop-status ${kind}`.trim();
        root.textContent = message ? I18n.t(message) : '';
    }
    function paintChosen() {
        el('trip-free-stop-geocode-candidates')?.querySelectorAll?.('[role="option"]')
            .forEach((node, index) => node.setAttribute('aria-selected', String(index === chosenIndex)));
    }
    function renderCandidates(items = [], provider = '') {
        candidates = items.filter(item => Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lng)));
        chosenIndex = -1;
        const root = el('trip-free-stop-geocode-candidates');
        if (!root) return;
        root.innerHTML = candidates.map((item, index) => `<button type="button" class="btn btn-secondary btn-sm"
            role="option" aria-selected="false" onclick="TripFreeStopForm.chooseCandidate(${index})">${escapeHtml(
                item.normalized_address || `${item.lat}, ${item.lng}`
            )} · ${escapeHtml(item.confidence || I18n.t('Approximate'))}</button>`).join('');
        root.hidden = !candidates.length;
        if (candidates.length) status(I18n.t('{count} locations found via {provider}. Choose one to confirm its coordinates.', {
            count: candidates.length, provider: provider || I18n.t('External service')
        }), 'success');
    }
    function chooseCandidate(index) {
        const item = candidates[index];
        if (!item) return;
        set('trip-free-stop-lat', Number(item.lat).toFixed(6));
        set('trip-free-stop-lng', Number(item.lng).toFixed(6));
        chosenIndex = index;
        paintChosen();
        window.TripFreeStopDraft?.mark?.();
        status(I18n.t('Location selected: {address}', {
            address: item.normalized_address || `${item.lat}, ${item.lng}`
        }), 'success');
    }
    function categoryChanged() {
        const waypoint = WAYPOINT_CATEGORIES.includes(value('trip-free-stop-category'));
        const field = el('trip-free-stop-stay-field');
        const note = el('trip-free-stop-waypoint-note');
        if (field) field.hidden = waypoint;
        if (note) note.hidden = !waypoint;
    }
    function open(stopId = null) {
        if (window.TripBriefingDraft?.guard?.()) return;
        if (!State.currentTripPlan?.id) {
            alert(I18n.t('Create or select a saved trip plan before adding a personal stop.'));
            return;
        }
        const currentId = value('trip-free-stop-id');
        const editorOpen = !el('trip-free-stop-editor')?.hidden;
        if (editorOpen && window.TripFreeStopDraft?.isDirty?.()) {
            if (String(stopId || '') === currentId) { el('trip-free-stop-name')?.focus(); return; }
            if (!window.TripFreeStopDraft.confirmDiscard()) return;
        }
        contextVersion += 1;
        window.TripFreeStopActions?.cancelGeocode?.();
        const stop = (State.currentTripPlan.stops || []).find(item => item.id === stopId && item.stop_kind === 'free');
        const values = stop || {};
        set('trip-free-stop-id', stop?.id || '');
        set('trip-free-stop-row-version', stop?.row_version || '');
        set('trip-free-stop-category', CATEGORIES.includes(stop?.category) ? stop.category : 'rest');
        set('trip-free-stop-stay', TripDuration.toDisplayDays(stop
            ? TripDuration.readStopDuration(stop) : 2));
        set('trip-free-stop-period', ['auto', 'AM', 'PM'].includes(stop?.preferred_period) ? stop.preferred_period : 'auto');
        set('trip-free-stop-confirmation', stop?.confirmation_status || 'unconfirmed');
        set('trip-free-stop-name', stop?.location_name || stop?.customer_name || '');
        ['address', 'city', 'country', 'lat', 'lng', 'visit_purpose', 'notes'].forEach(field => {
            const source = field === 'notes' ? values.notes : values[field];
            set(`trip-free-stop-${field.replace('visit_purpose', 'purpose')}`, source);
        });
        set('trip-free-stop-postal', '');
        renderCandidates([]);
        status('');
        categoryChanged();
        window.TripFreeStopDraft?.reset?.();
        const editor = el('trip-free-stop-editor');
        if (editor) editor.hidden = false;
        el('trip-add-free-stop')?.setAttribute('aria-expanded', 'true');
        const title = el('trip-free-stop-editor-title');
        if (title) title.textContent = I18n.t(stop ? 'Edit personal stop' : 'Add personal stop');
        el('trip-free-stop-name')?.focus();
    }
    function close(options = {}) {
        if (!options.force && !window.TripFreeStopDraft?.confirmDiscard?.()) return false;
        contextVersion += 1;
        window.TripFreeStopActions?.cancelGeocode?.();
        const editor = el('trip-free-stop-editor');
        if (editor) editor.hidden = true;
        el('trip-add-free-stop')?.setAttribute('aria-expanded', 'false');
        renderCandidates([]);
        status('');
        window.TripFreeStopDraft?.reset?.();
        return true;
    }
    function payload() {
        const rawLat = value('trip-free-stop-lat');
        const rawLng = value('trip-free-stop-lng');
        const lat = rawLat === '' ? NaN : Number(rawLat);
        const lng = rawLng === '' ? NaN : Number(rawLng);
        const durationHalfDays = TripDuration.parseDisplayDays(value('trip-free-stop-stay'));
        if (!value('trip-free-stop-name')) throw new Error(I18n.t('Location name is required.'));
        if (durationHalfDays == null) {
            throw new Error(I18n.t('Stop duration must be 0.5 to 30 days in 0.5-day increments.'));
        }
        if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lng) || lng < -180 || lng > 180) {
            throw new Error(I18n.t('Choose a location result or enter valid latitude and longitude.'));
        }
        return {
            category: CATEGORIES.includes(value('trip-free-stop-category')) ? value('trip-free-stop-category') : 'other',
            location_name: value('trip-free-stop-name'), address: value('trip-free-stop-address') || null,
            city: value('trip-free-stop-city') || null, country: value('trip-free-stop-country') || null,
            lat, lng, duration_half_days: durationHalfDays,
            preferred_period: ['auto', 'AM', 'PM'].includes(value('trip-free-stop-period'))
                ? value('trip-free-stop-period') : 'auto',
            confirmation_status: value('trip-free-stop-confirmation') || 'unconfirmed',
            visit_purpose: value('trip-free-stop-purpose') || null, notes: value('trip-free-stop-notes') || null,
        };
    }
    function geocodeFields() {
        return { address: value('trip-free-stop-address'), city: value('trip-free-stop-city'),
            country: value('trip-free-stop-country'), postal_code: value('trip-free-stop-postal') };
    }
    function setBusy(busy) {
        ['trip-free-stop-save', 'trip-free-stop-geocode'].forEach(id => { if (el(id)) el(id).disabled = busy; });
        el('trip-free-stop-editor')?.setAttribute('aria-busy', String(Boolean(busy)));
    }
    function locationTextChanged() {
        window.TripFreeStopActions?.cancelGeocode?.();
        renderCandidates([]);
        set('trip-free-stop-lat', '');
        set('trip-free-stop-lng', '');
        window.TripFreeStopDraft?.mark?.();
        status('Location text changed. Search again or manually confirm the coordinates.', 'warning');
    }
    window.TripFreeStopForm = Object.freeze({ open, close, payload, geocodeFields, renderCandidates,
        chooseCandidate, status, setBusy, categoryChanged, editingId: () => value('trip-free-stop-id'),
        rowVersion: () => Number(value('trip-free-stop-row-version')) || null,
        contextVersion: () => contextVersion,
        isOpen: () => Boolean(el('trip-free-stop-editor') && !el('trip-free-stop-editor').hidden),
        locationTextChanged });
})();
