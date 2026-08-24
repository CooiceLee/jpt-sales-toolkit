/** Independent dirty boundary for one customer-visit briefing editor. */
(function() {
    const ARRAYS = Object.freeze(['customer_team', 'contacts', 'channel_partner_companions', 'participants', 'equipment', 'agenda_items']);
    const blanks = Object.freeze({
        customer_team: () => ({ name: '', title: '', phone: '', email: '', notes: '' }),
        contacts: () => ({ source_contact_id: null, name: '', position: '', email: '', phone: '', role: '', notes: '' }),
        channel_partner_companions: () => ({ company_name: '', name: '', position: '', phone: '', email: '', role: '', notes: '' }),
        participants: () => ({ user_id: null, display_name: '', role: '', responsibility: '', notes: '' }),
        equipment: () => ({ kind: 'demo', model: '', specification: '', quantity: null, owner_team: '', notes: '' }),
        agenda_items: () => ({ topic: '', owner: '', preparation: '', expected_outcome: '' }),
    });
    let dirty = false;
    let stopId = null;
    let record = null;
    const clone = value => typeof structuredClone === 'function'
        ? structuredClone(value) : JSON.parse(JSON.stringify(value));

    function normalizeRecord(data = {}) {
        const savedLocation = data.location || {};
        const effectiveLocation = data.effective_location || {};
        const location = savedLocation.use_customer_default === false ? savedLocation : {
            ...effectiveLocation,
            ...Object.fromEntries(Object.entries(savedLocation).filter(([, value]) => value !== null && value !== '')),
        };
        return {
            ...data, row_version: data.row_version ?? null, stop_row_version: data.stop_row_version ?? null,
            confirmation_status: data.confirmation_status || 'unconfirmed', timezone: data.timezone || '',
            location: {
                name: location.name || '', address: location.address || '', city: location.city || '',
                postal_code: location.postal_code || '', country: location.country || '',
                lat: location.lat ?? '', lng: location.lng ?? '',
                use_customer_default: location.use_customer_default !== false,
            },
            ...Object.fromEntries(ARRAYS.map(key => [key, Array.isArray(data[key]) ? clone(data[key]) : []])),
        };
    }

    function blankRow(kind) {
        return blanks[kind]();
    }

    function renderStatus(message = '') {
        const root = document.getElementById('trip-briefing-draft-status');
        if (!root) return;
        root.textContent = message || (dirty ? I18n.t('Visit preparation changes are not saved.') : '');
        root.classList.toggle('has-warning', Boolean(message || dirty));
    }

    function load(nextStopId, nextRecord) {
        stopId = nextStopId || null;
        record = nextRecord ? clone(nextRecord) : null;
        dirty = false;
        renderStatus();
        return record;
    }

    function markDirty() {
        if (!record) return;
        dirty = true;
        renderStatus();
    }

    function markClean(nextRecord = record) {
        record = nextRecord ? clone(nextRecord) : null;
        dirty = false;
        renderStatus();
    }

    function reset() {
        stopId = null;
        record = null;
        dirty = false;
        renderStatus();
    }

    function guard(options = {}) {
        if (!dirty) return false;
        const message = I18n.t('Save or cancel customer visit preparation changes before continuing.');
        if (options.silent) notify(message); else alert(message);
        return true;
    }

    function confirmDiscard(message = 'Discard unsaved customer visit preparation changes?') {
        return !dirty || confirm(I18n.t(message));
    }

    function bindBeforeUnload() {
        window.addEventListener?.('beforeunload', event => {
            if (!dirty) return;
            event.preventDefault();
            event.returnValue = '';
        });
    }

    window.TripBriefingDraft = Object.freeze({
        load, markDirty, markClean, reset, guard, confirmDiscard,
        isDirty: () => dirty, getStopId: () => stopId, getRecord: () => record,
        setStatus: renderStatus, normalizeRecord, blankRow,
    });
    bindBeforeUnload();
})();
