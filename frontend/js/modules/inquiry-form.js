function renderPanelContent(tabId) {
    const container = document.getElementById('panel-content');
    const inq = State.currentInquiry;
    if (!inq) return;
    PanelDirtyState.reset();
    // The fields are being rebuilt, so nothing in them is unsaved any more.
    // An editor that saves through its own button - a sampling task, a
    // follow-up - refreshes this panel and nothing else, and the line went on
    // saying "unsaved changes" over a tab with no Save button to press.
    window.PanelSaveState?.show?.('clean');

    if (tabId === 'followup') {
        container.innerHTML = renderFollowupsTab(inq);
        return;
    }

    if (tabId === 'aftersales') {
        container.innerHTML = renderAftersalesTab(inq);
        return;
    }

    if (tabId === 'files') {
        container.innerHTML = renderFilesTab(inq);
        return;
    }

    if (tabId === 'sample') {
        container.innerHTML = SamplingModule.renderTab(inq);
        return;
    }

    if (tabId === 'quality') {
        DataQualityModule.render(inq.id);
        return;
    }

    // Get fields for this tab
    const fieldGroup = State.config.fields?.field_groups?.[tabId];
    if (!fieldGroup) {
        container.innerHTML = `<div class="empty-state">${escapeHtml(I18n.t('No fields configured for this tab.'))}</div>`;
        return;
    }

    const fields = Object.entries(fieldGroup.fields);
    let html = fields.map(([name, def]) => {
        const value = getFieldValue(inq, name);
        const editable = def.editable !== false;

        // Add help text for contact fields
        let helpText = '';
        if (tabId === 'customer' && (name === 'contact_name' || name === 'email')) {
            if (name === 'contact_name') {
                helpText = `<div class="form-help">${escapeHtml(I18n.t('Enter at least a contact name or email address.'))}</div>`;
            } else if (name === 'email') {
                helpText = `<div class="form-help">${escapeHtml(I18n.t('Email format: example@company.com'))}</div>`;
            }
        }

        return `
            <div class="form-group">
                <label class="form-label">${escapeHtml(def.label)}</label>
                ${editable ? renderFormField(name, def, value) : `<div class="form-static">${escapeHtml(value || '-')}</div>`}
                ${helpText}
                <div class="form-error" id="error-${name}" style="display:none;"></div>
            </div>
        `;
    }).join('');

    // Add Assignment management for basic tab (leader only)
    if (tabId === 'basic' && State.user?.role === 'leader') {
        html += renderAssignmentSection(inq);
    }

    if (tabId === 'basic' || tabId === 'deal') {
        html += renderLeadClosureSection(inq);
    }

    container.innerHTML = html;

    // Load assignment users after rendering
    if (tabId === 'basic' && State.user?.role === 'leader') {
        loadAssignmentUsers();
    }

    // Add contact validation for customer tab
    if (tabId === 'customer') {
        setupContactValidation();
        setupPrimaryContactSelection(container);
    }
}
