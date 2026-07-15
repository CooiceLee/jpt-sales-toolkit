function getLeadPrimaryContact(lead, customer = lead?.customer) {
    const contacts = customer?.contacts || [];
    if (lead?.primary_contact_id) {
        return contacts.find(contact => contact.id === lead.primary_contact_id) || null;
    }
    return contacts.find(contact => contact.is_primary) || null;
}

function renderPrimaryContactSelect(value) {
    const contacts = State.currentInquiry?._customer?.contacts || [];
    return `
        <select class="form-select" name="primary_contact_id">
            <option value="">Select contact...</option>
            ${contacts.map(contact => {
                const label = contact.name || contact.email || contact.id;
                return `<option value="${escapeHtml(contact.id)}" ${value === contact.id ? 'selected' : ''}>${escapeHtml(label)}</option>`;
            }).join('')}
        </select>
    `;
}

function setupPrimaryContactSelection(container) {
    const select = container.querySelector('select[name="primary_contact_id"]');
    if (!select) return;
    select.addEventListener('change', () => {
        const contacts = State.currentInquiry?._customer?.contacts || [];
        const contact = contacts.find(item => item.id === select.value) || {};
        const values = {
            contact_name: contact.name,
            contact_position: contact.position,
            email: contact.email,
            phone: contact.phone,
        };
        Object.entries(values).forEach(([name, value]) => {
            const field = container.querySelector(`[name="${name}"]`);
            if (field) field.value = value || '';
        });
    });
}

function getFieldValue(inq, fieldName) {
    // Map field names to lead/customer properties
    const lead = inq._lead;
    const customer = inq._customer;
    const primaryContact = getLeadPrimaryContact(lead, customer);

    // Field name mappings
    const fieldMap = {
        // Basic fields
        'inquiry_id': lead?.display_id,
        'inquiry_date': lead?.inquiry_date || lead?.created_at,
        'source_channel': lead?.source_channel,
        'original_email': lead?.original_email,
        'assigned_sales': (lead?.assignments || []).find(a => a.assignment_type === 'owner')?.user_name || lead?.owner_name || lead?.owner_id,

        // Customer fields - from customer object
        'primary_contact_id': primaryContact?.id || lead?.primary_contact_id,
        'contact_name': primaryContact?.name,
        'contact_position': primaryContact?.position,
        'company_name': customer?.display_name,
        'email': primaryContact?.email,
        'phone': primaryContact?.phone,
        'address': customer?.address,
        'city': customer?.city,
        'postal_code': customer?.postal_code,
        'country': customer?.country,
        'lat': customer?.lat,
        'lng': customer?.lng,
        'region': customer?.region,
        'customer_type': customer?.customer_type,
        'industry': customer?.industry,
        'language': customer?.language,
        'website': customer?.website,
        'company_description': customer?.company_description,
        'company_size': customer?.company_size,

        // Requirement fields
        'product_category': lead?.product_category,
        'product_series': lead?.product_series,
        'power_range': lead?.power_range,
        'wavelength': lead?.wavelength,
        'application': lead?.application,
        'material': lead?.material,
        'quantity_text': lead?.quantity_text,
        'special_requirements': lead?.special_requirements,
        'potential_needs': lead?.potential_needs,

        // Evaluation fields
        'quality_rating': lead?.quality_grade,
        'urgency': lead?.urgency,
        'estimated_value': lead?.estimated_value,
        'stage': lead?.sales_stage,
        'next_followup_date': lead?.next_followup_date,

        // Deal fields
        'quotation_id': lead?.quotation_id,
        'quotation_date': lead?.quotation_date,
        'po_number': lead?.po_number,
        'po_date': lead?.po_date,
        'deal_amount': lead?.deal_amount,
        'currency': lead?.currency,
        'products_detail': lead?.products_detail,

        // Fulfillment fields
        'fulfillment_status': lead?.fulfillment_status,
    };

    return fieldMap[fieldName] ?? '';
}
