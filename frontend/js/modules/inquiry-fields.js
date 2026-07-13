function getFieldValue(inq, fieldName) {
    // Map field names to lead/customer properties
    const lead = inq._lead;
    const customer = inq._customer;

    // Field name mappings
    const fieldMap = {
        // Basic fields
        'inquiry_id': lead?.display_id,
        'inquiry_date': lead?.inquiry_date || lead?.created_at,
        'source_channel': lead?.source_channel,
        'original_email': lead?.original_email,
        'assigned_sales': (lead?.assignments || []).find(a => a.assignment_type === 'owner')?.user_name || lead?.owner_name || lead?.owner_id,

        // Customer fields - from customer object
        'contact_name': customer?.contacts?.[0]?.name,
        'contact_position': customer?.contacts?.[0]?.position,
        'company_name': customer?.display_name,
        'email': customer?.contacts?.[0]?.email,
        'phone': customer?.contacts?.[0]?.phone,
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

