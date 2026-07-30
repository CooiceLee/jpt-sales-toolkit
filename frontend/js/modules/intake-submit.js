(function () {
    'use strict';

    function collectEditedFields() {
        const fields = {};
        document.querySelectorAll('#parsed-fields-list input').forEach(input => {
            if (input.value.trim()) fields[input.dataset.field] = input.value.trim();
        });
        return fields;
    }

    async function matchCustomer(fields) {
        if (!fields.email && !fields.company_name) return null;
        try {
            const matches = await ApiClient.matchCustomers(fields.email, fields.company_name);
            return matches[0]?.id || null;
        } catch (err) {
            return null;
        }
    }

    function buildCustomer(fields) {
        return {
            display_name: fields.company_name || fields.contact_name || 'Unknown',
            country: fields.country || null,
            city: fields.city || null,
            postal_code: fields.postal_code || null,
            region: fields.region || null,
            industry: fields.industry || null,
            website: fields.website || null,
        };
    }

    function buildContact(fields) {
        if (!fields.contact_name && !fields.email) return null;
        return {
            name: fields.contact_name || '',
            position: fields.contact_position || null,
            email: fields.email || null,
            phone: fields.phone || null,
            is_primary: true,
        };
    }

    function buildLead(fields, originalEmail) {
        return {
            title: fields.product || fields.inquiry_type || 'New Inquiry',
            source_channel: 'Email',
            original_email: originalEmail,
            sales_stage: 'New',
            product_category: fields.product_category || fields.product || null,
            application: fields.application || null,
            inquiry_date: fields.inquiry_date || null,
            product_series: fields.product_series || null,
            power_range: fields.power_range || null,
            wavelength: fields.wavelength || null,
            material: fields.material || null,
            special_requirements: fields.special_requirements || null,
            potential_needs: fields.potential_needs || null,
        };
    }

    async function saveAsInquiry() {
        const parsedData = window.JptIntake?.getParsedData();
        if (!parsedData) return;

        const fields = collectEditedFields();
        try {
            const customerId = await matchCustomer(fields);
            const isNewCustomer = !customerId;
            const result = await ApiClient.submitIntake({
                is_new_customer: isNewCustomer,
                customer_id: customerId,
                customer: isNewCustomer ? buildCustomer(fields) : null,
                contact: buildContact(fields),
                lead: buildLead(fields, parsedData.original_email),
                owner_id: State.user.id,
            });
            alert(I18n.t('Lead created: {id}', { id: result.display_id || result.lead_id }));
            window.clearParser();
            switchModule('handler');
        } catch (err) {
            console.error('Save error:', err);
            alert(I18n.t('Error creating lead: {error}', {
                error: I18n.t(err.message || 'Unknown error')
            }));
        }
    }

    window.saveAsInquiry = saveAsInquiry;
})();
