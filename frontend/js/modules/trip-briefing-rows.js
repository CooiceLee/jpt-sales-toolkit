/** Structured row rendering for customer visit preparation arrays. */
(function() {
    const h = value => escapeHtml(value ?? '');
    const field = (kind, index, key, value, placeholder = key, attributes = '') =>
        `<input class="form-input" data-field="${h(key)}" value="${h(value)}" placeholder="${h(I18n.t(placeholder))}" ${attributes}>`;
    const area = (key, value, placeholder = key) =>
        `<textarea class="form-input" rows="2" data-field="${h(key)}" placeholder="${h(I18n.t(placeholder))}">${h(value)}</textarea>`;

    function controls(kind, index, total) {
        return `<div class="trip-briefing-row-actions">
            <button type="button" class="btn btn-secondary btn-sm" onclick="TripBriefingForm.arrayAction('${kind}','up',${index})" ${index ? '' : 'disabled'}>${h(I18n.t('Up'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="TripBriefingForm.arrayAction('${kind}','down',${index})" ${index < total - 1 ? '' : 'disabled'}>${h(I18n.t('Down'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="TripBriefingForm.arrayAction('${kind}','remove',${index})">${h(I18n.t('Remove'))}</button>
        </div>`;
    }

    function contactSelect(item, index, available) {
        const selected = item.source_contact_id || '';
        return `<select class="form-input" data-field="source_contact_id" onchange="TripBriefingForm.chooseContact(${index},this.value)">
            <option value="">${h(I18n.t('Temporary or manual contact'))}</option>
            ${(available || []).map(contact => {
                const id = contact.id || contact.contact_id || '';
                const label = [contact.name, contact.position, contact.email || contact.phone].filter(Boolean).join(' · ');
                return `<option value="${h(id)}" ${String(id) === String(selected) ? 'selected' : ''}>${h(label || id)}</option>`;
            }).join('')}</select>`;
    }

    function participantSelect(item, index, available) {
        const selected = item.user_id || '';
        return `<select class="form-input" data-field="user_id" onchange="TripBriefingForm.chooseParticipant(${index},this.value)">
            <option value="">${h(I18n.t('Select an active team member'))}</option>
            ${(available || []).map(user => {
                const id = user.id || user.user_id || '';
                const label = [user.display_name || user.name, user.role].filter(Boolean).join(' · ');
                return `<option value="${h(id)}" ${String(id) === String(selected) ? 'selected' : ''}>${h(label || id)}</option>`;
            }).join('')}</select>`;
    }

    function renderRow(kind, item, index, total, source = {}) {
        let body = '';
        if (kind === 'customer_team') body = [
            field(kind, index, 'name', item.name, 'Name'), field(kind, index, 'title', item.title, 'Title'),
            field(kind, index, 'phone', item.phone, 'Phone'), field(kind, index, 'email', item.email, 'Email'),
            area('notes', item.notes, 'Notes'),
        ].join('');
        if (kind === 'contacts') body = [
            contactSelect(item, index, source.available_contacts), field(kind, index, 'name', item.name, 'Name'),
            field(kind, index, 'position', item.position, 'Position'), field(kind, index, 'email', item.email, 'Email'),
            field(kind, index, 'phone', item.phone, 'Phone'), field(kind, index, 'role', item.role, 'Visit role'),
            area('notes', item.notes, 'Notes'),
        ].join('');
        if (kind === 'channel_partner_companions') body = [
            field(kind, index, 'company_name', item.company_name, 'Company Name'), field(kind, index, 'name', item.name, 'Name'),
            field(kind, index, 'position', item.position, 'Position'), field(kind, index, 'phone', item.phone, 'Phone'), field(kind, index, 'email', item.email, 'Email'),
            field(kind, index, 'role', item.role, 'Visit role'), area('notes', item.notes, 'Notes'),
        ].join('');
        if (kind === 'participants') body = [
            participantSelect(item, index, source.available_participants),
            field(kind, index, 'display_name', item.display_name, 'Display name', 'readonly'),
            field(kind, index, 'role', item.role, 'Role', 'readonly'),
            field(kind, index, 'responsibility', item.responsibility, 'Responsibility'),
            area('notes', item.notes, 'Notes'),
        ].join('');
        if (kind === 'equipment') body = [
            `<select class="form-input" data-field="kind">
                ${['demo', 'po', 'other'].map(value => `<option value="${value}" ${item.kind === value ? 'selected' : ''}>${h(I18n.t({ demo: 'Demo laser', po: 'PO laser', other: 'Other' }[value]))}</option>`).join('')}
            </select>`,
            field(kind, index, 'model', item.model, 'Model'),
            field(kind, index, 'specification', item.specification, 'Specification'),
            field(kind, index, 'quantity', item.quantity, 'Quantity'),
            field(kind, index, 'owner_team', item.owner_team, 'Owner team'), area('notes', item.notes, 'Notes'),
        ].join('');
        if (kind === 'agenda_items') body = [
            field(kind, index, 'topic', item.topic, 'Visiting topic'), field(kind, index, 'owner', item.owner, 'Owner'),
            area('preparation', item.preparation, 'Preparation'), area('expected_outcome', item.expected_outcome, 'Expected outcome'),
        ].join('');
        return `<div class="trip-briefing-row" data-row-index="${index}"><div class="trip-briefing-row-grid">${body}</div>${controls(kind, index, total)}</div>`;
    }

    function renderSection(kind, title, items, source) {
        return `<section class="trip-briefing-section"><div class="trip-briefing-section-head"><h4>${h(I18n.t(title))}</h4>
            <div><button type="button" class="btn btn-secondary btn-sm" onclick="TripBriefingForm.arrayAction('${kind}','clear')">${h(I18n.t('Clear all'))}</button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="TripBriefingForm.arrayAction('${kind}','add')">+ ${h(I18n.t('Add'))}</button></div></div>
            <div data-briefing-array="${h(kind === 'agenda_items' ? 'agenda' : kind)}" data-briefing-array-key="${h(kind)}">
                ${(items || []).map((item, index) => renderRow(kind, item, index, items.length, source)).join('')
                    || `<div class="trip-briefing-empty">${h(I18n.t('No entries. Add one when needed.'))}</div>`}
            </div></section>`;
    }

    function syncModel(model, arrays) {
        arrays.forEach(kind => {
            const root = document.querySelector(`[data-briefing-array-key="${kind}"]`);
            model[kind] = Array.from(root?.querySelectorAll('[data-row-index]') || []).map((row, index) => {
                const item = {};
                row.querySelectorAll('[data-field]').forEach(input => { item[input.dataset.field] = input.value.trim(); });
                item.sequence_no = index + 1;
                return item;
            });
        });
        model.confirmation_status = document.getElementById('trip-briefing-confirmation')?.value || 'unconfirmed';
        model.timezone = document.getElementById('trip-briefing-timezone')?.value?.trim() || null;
        document.querySelectorAll('[data-location-field]').forEach(input => { model.location[input.dataset.locationField] = input.value.trim(); });
        model.location.use_customer_default = Boolean(document.getElementById('trip-briefing-use-default')?.checked);
    }

    function suggestionsHtml(source) {
        const suggestions = source?.lead_suggestions || source?.suggestions || [];
        const list = Array.isArray(suggestions) ? suggestions : [suggestions];
        if (!list.filter(Boolean).length) return '';
        return `<div class="trip-briefing-suggestions"><strong>${h(I18n.t('Lead suggestions'))}</strong>
            <small>${h(I18n.t('Review the suggested details, then choose what to add.'))}</small>
            ${list.map((item, index) => `<button type="button" class="btn btn-secondary btn-sm" onclick="TripBriefingForm.applySuggestion(${index})">
                ${h(I18n.t('Suggest from Lead'))} ${h(item?.label || item?.lead_display_id || index + 1)}</button>`).join('')}</div>`;
    }

    function locationHtml(model) {
        const location = model.location;
        const disabled = location.use_customer_default ? 'disabled' : '';
        const input = (key, placeholder, type = 'text') => `<input type="${type}" class="form-input" data-location-field="${key}"
            value="${h(location[key])}" placeholder="${h(I18n.t(placeholder))}" ${disabled}
            ${['name','address','city','postal_code','country'].includes(key) ? `onchange="TripBriefingForm.locationIdentityChanged('${key}')"` : ''}>`;
        return `<section class="trip-briefing-section"><div class="trip-briefing-section-head"><h4>${h(I18n.t('Visit location'))}</h4></div>
            <label class="trip-check"><input type="checkbox" id="trip-briefing-use-default" ${location.use_customer_default ? 'checked' : ''}
                onchange="TripBriefingForm.toggleLocationDefault(this.checked)"><span>${h(I18n.t('Use the customer default location'))}</span></label>
            <div class="trip-briefing-location-grid">${input('name', 'Location name')}${input('address', 'Address')}
                ${input('city', 'City')}${input('postal_code', 'Postal Code')}${input('country', 'Country')}
                <button type="button" class="btn btn-secondary btn-sm" id="trip-briefing-location-search" onclick="TripBriefingActions.searchLocation()" ${disabled}>${h(I18n.t('Find location'))}</button>
                ${input('lat', 'Latitude', 'number')}${input('lng', 'Longitude', 'number')}</div>
            <div id="trip-briefing-location-status" class="trip-free-stop-status" role="status" aria-live="polite"></div>
            <div id="trip-briefing-location-candidates" class="trip-free-stop-candidates"></div></section>`;
    }

    function renderForm(model, source, stop) {
        const root = document.getElementById('trip-briefing-editor');
        if (!root || !model) return;
        root.hidden = false;
        root.innerHTML = `<div class="trip-briefing-head"><div><strong>${h(stop?.customer_name || I18n.t('Customer visit preparation'))}</strong>
            <small>${h([stop?.planned_date, stop?.planned_start_period].filter(Boolean).join(' ') || I18n.t('Not scheduled'))}</small></div>
            <button type="button" class="trip-free-stop-close" onclick="TripBriefingActions.close()" aria-label="${h(I18n.t('Close'))}">&times;</button></div>
            <div class="trip-briefing-scroll" oninput="TripBriefingDraft.markDirty()" onchange="TripBriefingDraft.markDirty()">
                <div class="trip-briefing-summary-grid"><label class="trip-field-label"><span>${h(I18n.t('Confirmation status'))}</span>
                    <select class="form-input" id="trip-briefing-confirmation">${[
                        ['unconfirmed','Unconfirmed'],['tentative','Tentative'],['confirmed','Confirmed'],
                        ['needs_reconfirmation','Needs reconfirmation'],['cancelled','Cancelled'],
                    ].map(([value,label]) => `<option value="${value}" ${model.confirmation_status === value ? 'selected' : ''}>${h(I18n.t(label))}</option>`).join('')}</select></label>
                    <label class="trip-field-label"><span>${h(I18n.t('Timezone'))}</span><input class="form-input" id="trip-briefing-timezone" value="${h(model.timezone)}" placeholder="Europe/Berlin"></label></div>
                ${suggestionsHtml(source)}${locationHtml(model)}
                ${renderSection('contacts', 'Customer contacts (from the customer record)', model.contacts, source)}${renderSection('customer_team', 'Other customer attendees (typed in)', model.customer_team, source)}
                ${renderSection('channel_partner_companions', 'Channel partner companions (if any)', model.channel_partner_companions, source)}${renderSection('participants', 'JPT internal participants', model.participants, source)}
                ${renderSection('equipment', 'Equipment', model.equipment, source)}
                ${renderSection('agenda_items', 'Visiting topics', model.agenda_items, source)}
            </div><div id="trip-briefing-draft-status" class="trip-briefing-draft-status" role="status" aria-live="polite"></div>
            <div class="trip-briefing-footer"><button type="button" class="btn btn-secondary" id="trip-briefing-refresh" onclick="TripBriefingActions.refreshLatest()">${h(I18n.t('Refresh latest'))}</button>
                <button type="button" class="btn btn-secondary" onclick="TripBriefingActions.close()">${h(I18n.t('Cancel'))}</button>
                <button type="button" class="btn btn-primary" id="trip-briefing-save" onclick="TripBriefingActions.save()">${h(I18n.t('Save preparation'))}</button></div>`;
        TripBriefingDraft.setStatus();
    }

    window.TripBriefingRows = Object.freeze({ renderSection, syncModel, renderForm });
})();
