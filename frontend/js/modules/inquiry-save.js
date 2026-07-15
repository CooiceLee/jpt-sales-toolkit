// ===== Save Inquiry =====
window.saveInquiry = async function() {
    const leadId = State.currentInquiry?.id;
    const rowVersion = State.currentInquiry?.row_version;
    if (!leadId) return;
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
    try {
        const customerId = State.currentInquiry?._customer?.id;
        const customerRowVersion = State.currentInquiry?._customer?.row_version;
        const contacts = State.currentInquiry?._customer?.contacts || [];
        const selectedContactId = content.querySelector('[name="primary_contact_id"]')?.value;
        const existingContact = selectedContactId
            ? contacts.find(contact => contact.id === selectedContactId)
            : getLeadPrimaryContact(State.currentInquiry?._lead, State.currentInquiry?._customer);
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
        // Update customer if there are customer field changes
        if (customerId && Object.keys(customerFields).length > 0) {
            await ApiClient.updateCustomer(customerId, customerFields, customerRowVersion);
        }
        if (customerId && hasContactValue) {
            if (existingContact?.id) {
                await ApiClient.updateCustomerContact(customerId, existingContact.id, contactFields);
            } else {
                await ApiClient.createCustomerContact(customerId, {
                    ...contactFields,
                    is_primary: true
                });
            }
        }
        // Update lead if there are lead field changes
        if (Object.keys(leadFields).length > 0) {
            await ApiClient.updateLead(leadId, leadFields, rowVersion);
        }
        // Refresh lead data (includes customer)
        const lead = await ApiClient.getLead(leadId);
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

        notify('Changes saved');
    } catch (err) {
        if (err.name === 'ConflictError') {
            alert(`Conflict: ${err.message}. Please refresh and try again.`);
        } else {
            console.error('Save error:', err);
            const errMsg = err.message || 'Unknown error';

            // Handle contact validation errors with field-specific display
            if (errMsg.includes('email') || errMsg.includes('contact') || errMsg.includes('name')) {
                handleContactValidationError(errMsg);
            } else {
                alert('Error saving changes: ' + errMsg);
            }
        }
    }
};
