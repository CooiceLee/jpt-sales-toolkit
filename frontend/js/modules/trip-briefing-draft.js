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
        const record = {
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
        // On a team trip, a visit that names nobody is attended by everybody.
        // Shown as an empty list that reads as "nobody is going", so the team
        // is filled in - but only for reading. The plan keeps meaning "whoever
        // is travelling" until the reader actually changes the list, so a
        // member who joins the trip later still joins this visit.
        if (!record.participants.length
            && State.currentTripPlan?.planning_mode === 'team') {
            record.participants = (State.currentTripPlan.members || []).map(
                (member, index) => ({
                    user_id: member.user_id,
                    display_name: member.display_name || member.user_id,
                    role: member.role || '', responsibility: '',
                    sequence_no: index + 1,
                })
            );
        }
        return record;
    }

    /** Whether this list still means "whoever is travelling on this trip".

    Compared against the team rather than tracked as a flag: a flag has to be
    cleared everywhere the list can be touched, and one missed place turns the
    inherited list into a fixed one without anybody noticing.
    */
    function isWholeTeam(participants) {
        if (State.currentTripPlan?.planning_mode !== 'team') return false;
        const members = State.currentTripPlan.members || [];
        const rows = participants || [];
        if (!members.length || rows.length !== members.length) return false;
        // Anything typed onto a row is a decision about that person, so the
        // list is no longer simply whoever happens to be travelling.
        if (rows.some(row => String(row.responsibility || '').trim()
            || String(row.notes || '').trim())) return false;
        const going = new Set(members.map(member => member.user_id));
        return rows.every(row => going.has(row.user_id));
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
        isWholeTeam,
        isDirty: () => dirty, getStopId: () => stopId, getRecord: () => record,
        setStatus: renderStatus, normalizeRecord, blankRow,
    });
    bindBeforeUnload();
})();
