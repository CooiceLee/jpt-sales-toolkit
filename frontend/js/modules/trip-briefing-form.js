/** Full-replacement customer visit preparation form. */
(function() {
    const ARRAYS = Object.freeze(['customer_team', 'contacts', 'channel_partner_companions', 'participants', 'equipment', 'agenda_items']);
    const clone = value => typeof structuredClone === 'function'
        ? structuredClone(value) : JSON.parse(JSON.stringify(value));
    let source = null;
    let model = null;

    function render() {
        const stop = (State.currentTripPlan?.stops || []).find(item => item.id === TripBriefingDraft.getStopId());
        TripBriefingRows.renderForm(model, source, stop);
    }

    function populate(data) {
        source = clone(data || {});
        model = TripBriefingDraft.normalizeRecord(data);
        render();
    }

    function syncFromDom() {
        if (!model) return;
        TripBriefingRows.syncModel(model, ARRAYS);
    }

    function arrayAction(kind, action, index = -1) {
        if (!ARRAYS.includes(kind) || !model) return;
        syncFromDom();
        const items = model[kind];
        if (action === 'add') items.push(TripBriefingDraft.blankRow(kind));
        if (action === 'clear') items.splice(0);
        if (action === 'remove' && index >= 0) items.splice(index, 1);
        if (action === 'up' && index > 0) [items[index - 1], items[index]] = [items[index], items[index - 1]];
        if (action === 'down' && index >= 0 && index < items.length - 1) [items[index + 1], items[index]] = [items[index], items[index + 1]];
        TripBriefingDraft.markDirty();
        render();
    }

    function chooseContact(index, id) {
        syncFromDom();
        const found = (source.available_contacts || []).find(item => String(item.id || item.contact_id) === String(id));
        model.contacts[index] = { ...model.contacts[index], ...(found ? {
            source_contact_id: found.id || found.contact_id, name: found.name || '', position: found.position || '',
            email: found.email || '', phone: found.phone || '',
        } : { source_contact_id: null }) };
        TripBriefingDraft.markDirty(); render();
    }

    function chooseParticipant(index, id) {
        syncFromDom();
        const found = (source.available_participants || []).find(item => String(item.id || item.user_id) === String(id));
        model.participants[index] = { ...model.participants[index], ...(found ? {
            user_id: found.id || found.user_id, display_name: found.display_name || found.name || '', role: found.role || '',
        } : { user_id: null }) };
        TripBriefingDraft.markDirty(); render();
    }

    function applySuggestion(index) {
        syncFromDom();
        const suggestions = source.lead_suggestions || source.suggestions || [];
        const suggestion = (Array.isArray(suggestions) ? suggestions : [suggestions])[index];
        if (!suggestion) return;
        const fields = suggestion.values || suggestion;
        let keptExisting = false;
        ARRAYS.forEach(key => {
            if (!Array.isArray(fields[key])) return;
            if (model[key].length) keptExisting = true;
            else model[key] = clone(fields[key]);
        });
        if (fields.location) {
            const hasLocation = ['name','address','city','postal_code','country','lat','lng']
                .some(key => String(model.location[key] ?? '').trim());
            if (hasLocation) keptExisting = true;
            else model.location = { ...model.location, ...fields.location };
        }
        if (fields.timezone && !model.timezone) model.timezone = fields.timezone;
        else if (fields.timezone) keptExisting = true;
        TripBriefingDraft.markDirty(); render();
        if (keptExisting) notify(I18n.t('Existing preparation was kept. Suggestions filled only empty sections.'));
    }

    function toggleLocationDefault(checked) {
        syncFromDom(); model.location.use_customer_default = Boolean(checked);
        TripBriefingDraft.markDirty(); render();
    }

    function setLocation(candidate) {
        syncFromDom();
        model.location = { ...model.location, name: candidate.name || model.location.name,
            address: candidate.normalized_address || model.location.address,
            lat: Number(candidate.lat).toFixed(6), lng: Number(candidate.lng).toFixed(6), use_customer_default: false };
        TripBriefingDraft.markDirty(); render();
    }

    function locationIdentityChanged() {
        syncFromDom();
        if (model.location.use_customer_default) return;
        model.location.lat = '';
        model.location.lng = '';
        const lat = document.querySelector('[data-location-field="lat"]');
        const lng = document.querySelector('[data-location-field="lng"]');
        if (lat) lat.value = '';
        if (lng) lng.value = '';
        window.TripBriefingActions?.cancelLocationSearch?.();
        TripBriefingDraft.markDirty();
        TripBriefingDraft.setStatus(I18n.t('Location text changed. Search again or manually confirm the coordinates.'));
    }

    function payload() {
        syncFromDom();
        if (!model.location.use_customer_default) {
            if (!String(model.location.name || '').trim()) {
                throw new Error(I18n.t('A location name is required for a custom visit location.'));
            }
            const rawLat = String(model.location.lat ?? '').trim();
            const rawLng = String(model.location.lng ?? '').trim();
            const lat = rawLat === '' ? NaN : Number(rawLat);
            const lng = rawLng === '' ? NaN : Number(rawLng);
            if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lng) || lng < -180 || lng > 180) {
                throw new Error(I18n.t('Confirm valid latitude and longitude for the custom visit location.'));
            }
            model.location.lat = lat; model.location.lng = lng;
        }
        model.customer_team = model.customer_team.filter(item =>
            ['name','title','phone','email','notes'].some(key => String(item[key] || '').trim()));
        if (model.customer_team.some(item => !String(item.name || '').trim())) {
            throw new Error(I18n.t('Each customer team row needs a name.'));
        }
        model.contacts = model.contacts.filter(item =>
            ['source_contact_id','name','position','email','phone','role','notes'].some(key => String(item[key] || '').trim()));
        if (model.contacts.some(item => ![item.name, item.email, item.phone].some(value => String(value || '').trim()))) {
            throw new Error(I18n.t('Each contact needs a name, email or phone number.'));
        }
        model.channel_partner_companions = model.channel_partner_companions.filter(item => ['company_name','name','position','phone','email','role','notes']
            .some(key => String(item[key] || '').trim()));
        if (model.channel_partner_companions.some(item => !String(item.name || '').trim()))
            throw new Error(I18n.t('Each channel partner companion needs a name.'));
        model.participants = model.participants.filter(item =>
            ['user_id','display_name','role','responsibility','notes'].some(key => String(item[key] || '').trim()));
        if (model.participants.some(item => !item.user_id)) {
            throw new Error(I18n.t('Select a team account for every internal participant.'));
        }
        model.equipment = model.equipment.filter(item =>
            ['model','specification','quantity','owner_team','notes'].some(key => item[key] !== '' && item[key] != null));
        if (model.equipment.some(item => !String(item.model || '').trim()
            && !String(item.specification || '').trim())) {
            throw new Error(I18n.t('Each equipment row needs a model or specification.'));
        }
        model.agenda_items = model.agenda_items.filter(item =>
            ['topic','owner','preparation','expected_outcome'].some(key => String(item[key] || '').trim()));
        if (model.agenda_items.some(item => !String(item.topic || '').trim())) {
            throw new Error(I18n.t('Each visiting topic needs a topic name.'));
        }
        ARRAYS.forEach(key => model[key].forEach((item, index) => { item.sequence_no = index + 1; }));
        return Object.fromEntries(['row_version','stop_row_version','confirmation_status','timezone','location', ...ARRAYS]
            .map(key => [key, clone(model[key] ?? null)]));
    }

    window.TripBriefingForm = Object.freeze({ populate, payload, arrayAction, chooseContact,
        chooseParticipant, applySuggestion, toggleLocationDefault, setLocation, locationIdentityChanged, render });
})();
