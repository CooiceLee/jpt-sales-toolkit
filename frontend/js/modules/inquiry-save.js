// ===== Save Inquiry =====
let inquirySaveEpoch = 0;

window.saveInquiry = async function() {
    const inquirySnapshot = State.currentInquiry;
    const leadId = inquirySnapshot?.id;
    const rowVersion = inquirySnapshot?.row_version;
    if (!leadId) return;
    const saveButton = document.getElementById('panel-save-btn');
    if (saveButton?.disabled) return;
    const panelSession = window.InquiryPanelSession?.capture?.()
        || Object.freeze({ leadId, generation: 0 });
    if (panelSession.leadId !== leadId) return;
    const saveRequest = Object.freeze({
        leadId,
        panelSession,
        saveEpoch: ++inquirySaveEpoch
    });
    const requestIsCurrent = () => inquirySaveEpoch === saveRequest.saveEpoch
        && (window.InquiryPanelSession?.isCurrent?.(panelSession)
            ?? State.currentInquiry?.id === saveRequest.leadId);
    const content = document.getElementById('panel-content');
    const inputs = content.querySelectorAll('input, select, textarea');
    const leadFields = {};
    const customerFields = {};
    const contactFields = {};
    inputs.forEach(input => {
        const name = input.name;
        if (!name) return;
        let value = input.value;
        if (input.type === 'number') {
            value = value === '' ? null : parseFloat(value);
        }
        if (value === 'true') value = true;
        if (value === 'false') value = false;
        if (name === 'primary_contact_id' && value === '') value = null;
        // Customer fields (mapped to customers table columns)
        const customerFieldNames = [
            'company_name', 'country', 'city', 'postal_code', 'address',
            'region', 'customer_type', 'industry', 'language', 'website',
            'company_description', 'company_size', 'lat', 'lng'
        ];
        // Separate lead vs customer fields
        if (customerFieldNames.includes(name)) {
            // Map UI field names to DB column names
            const customerFieldMap = {
                'company_name': 'display_name',
                'company_description': 'company_description'
            };
            customerFields[customerFieldMap[name] || name] = value;
        } else if (['contact_name', 'email', 'phone', 'contact_position'].includes(name)) {
            const contactFieldMap = {
                contact_name: 'name',
                contact_position: 'position',
                email: 'email',
                phone: 'phone'
            };
            contactFields[contactFieldMap[name]] = value;
        } else if (name !== 'assigned_sales') {
            // Lead fields
            const fieldMap = {
                'stage': 'sales_stage',
                'product': 'product_category',
                'quality_rating': 'quality_grade'
            };
            leadFields[fieldMap[name] || name] = value;
        }
    });
    if (saveButton) {
        saveButton.disabled = true;
        saveButton.dataset.inquirySaveEpoch = String(saveRequest.saveEpoch);
    }
    try {
        const customerId = inquirySnapshot?._customer?.id;
        const customerRowVersion = inquirySnapshot?._customer?.row_version;
        const contacts = inquirySnapshot?._customer?.contacts || [];
        const selectedContactId = content.querySelector('[name="primary_contact_id"]')?.value;
        const existingContact = selectedContactId
            ? contacts.find(contact => contact.id === selectedContactId)
            : getLeadPrimaryContact(inquirySnapshot?._lead, inquirySnapshot?._customer);
        const hasContactValue = Object.values(contactFields).some(value => value !== '' && value !== null && value !== undefined);
        const activeContactNameInput = content.querySelector('input[name="contact_name"]');
        const activeContactEmailInput = content.querySelector('input[name="email"]');
        if (activeContactNameInput && activeContactEmailInput) {
            const isContactPresent = activeContactNameInput.value.trim() || activeContactEmailInput.value.trim();
            const isContactValid = validateContactFields(activeContactNameInput, activeContactEmailInput);
            const isEmailValid = validateEmail(activeContactEmailInput);
            if (isContactPresent && (!isContactValid || !isEmailValid)) {
                return;
            }
        }
        const customer = customerId && Object.keys(customerFields).length > 0
            ? { ...customerFields, row_version: customerRowVersion }
            : null;
        const contact = customerId && hasContactValue
            ? {
                ...contactFields,
                contact_id: existingContact?.id || null,
                updated_at: existingContact?.updated_at || null,
                ...(!existingContact?.id ? { is_primary: true } : {})
            }
            : null;
        const leadPatch = Object.keys(leadFields).length > 0
            ? { ...leadFields, row_version: rowVersion }
            : null;
        const lead = await ApiClient.saveInquiryAggregate(leadId, {
            customer,
            contact,
            lead: leadPatch
        });
        if (!requestIsCurrent()) return;
        State.currentInquiry = {
            ...State.currentInquiry,
            stage: lead.sales_stage,
            product: lead.product_category,
            row_version: lead.row_version,
            _lead: lead,
            _customer: lead.customer
        };
        // Refresh active tab
        const activeTab = document.querySelector('.panel-tab.active');
        if (activeTab) renderPanelContent(activeTab.dataset.tab);
        // Refresh nav counts and the active module so stage badges move immediately.
        await refreshAllCounts();
        if (!requestIsCurrent()) return;

        notify(I18n.t('Changes saved'));
    } catch (err) {
        if (!requestIsCurrent()) {
            console.error('Stale inquiry save error:', err);
            return;
        }
        if (err.name === 'ConflictError') {
            alert(I18n.t('Conflict: {error}. Please refresh and try again.', {
                error: I18n.t(err.message || 'Unknown error')
            }));
        } else {
            console.error('Save error:', err);
            const errMsg = err.message || 'Unknown error';

            // Handle contact validation errors with field-specific display
            if (errMsg.includes('email') || errMsg.includes('contact') || errMsg.includes('name')) {
                handleContactValidationError(errMsg);
            } else {
                alert(I18n.t('Error saving changes: {error}', { error: I18n.t(errMsg) }));
            }
        }
    } finally {
        if (saveButton
            && requestIsCurrent()
            && saveButton.dataset.inquirySaveEpoch === String(saveRequest.saveEpoch)) {
            saveButton.disabled = false;
            delete saveButton.dataset.inquirySaveEpoch;
        }
    }
};
