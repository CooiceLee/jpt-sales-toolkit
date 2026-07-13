function moduleForLeadStage(lead) {
    const stage = lead?.sales_stage || lead?.stage;
    const serviceStatus = lead?.service_status || lead?.serviceStatus;
    if (serviceStatus && serviceStatus !== 'None') return 'aftersales';
    if (stage === 'Won') return 'fulfillment';
    if (stage === 'Quoted' || stage === 'Lost') return 'deal';
    if (stage === 'Following') return 'followup';
    return 'handler';
}

window.jumpToCustomerStageCards = async function(leadId, stage, customerId = '') {
    let lead = null;
    if (leadId) {
        try {
            lead = await ApiClient.getLead(leadId);
        } catch (err) {
            console.error('Load lead for review jump error:', err);
        }
    }
    State.stageFilters.search = lead?.customer?.display_name || '';
    State.stageFilters.customerId = customerId || lead?.customer_id || lead?.customer?.id || '';
    State.stageFilters.ownerId = '';
    State.stageFilters.techId = '';
    syncStageFilterInputs();
    const module = moduleForLeadStage(lead || { sales_stage: stage });
    switchModule(module);
    await loadModuleData(module);
    if (leadId) {
        await openInquiryPanel(leadId, module);
    }
};

window.focusReviewMapCustomer = async function(customerId) {
    switchModule('dashboard');
    setInputValue('map-stage-filter', '');
    setInputValue('map-outcome-filter', '');
    setInputValue('map-region-filter', '');
    setInputValue('map-quality-filter', '');
    await loadReviewMap();
    const marker = State.mapCustomerMarkers[customerId];
    if (!marker || !State.map) {
        try {
            switchModule('coordinate-review');
            await loadCoordinateReview();
            const customer = await ApiClient.getCustomer(customerId);
            openCoordinateCorrection(
                customer.id,
                customer.display_name || 'Customer',
                customer.lat ?? null,
                customer.lng ?? null,
                {
                    address: customer.address,
                    city: customer.city,
                    country: customer.country,
                    normalized_address: customer.normalized_address
                }
            );
            notify('Customer is not plotted on the review map. Opened coordinate correction.');
        } catch (err) {
            console.error('Coordinate correction fallback error:', err);
            alert('Customer location is not available on the review map.');
        }
        return;
    }
    State.map.setView(marker.getLatLng(), Math.max(State.map.getZoom(), 6));
    marker.openPopup();
};

function leadToCardItem(lead, extra = {}) {
    return {
        id: lead.id,
        inquiry_id: lead.display_id,
        company_name: lead.customer?.display_name || '',
        contact_name: lead.customer?.contacts?.[0]?.name || '',
        country: lead.customer?.country || '',
        city: lead.customer?.city || '',
        stage: lead.sales_stage,
        product_category: lead.product_category || '',
        title: lead.title,
        created_at: lead.created_at,
        inquiry_date: lead.inquiry_date,
        owner_name: (lead.assignments || []).find(item => item.assignment_type === 'owner')?.user_name || lead.owner_name || '',
        deal_amount: lead.deal_amount || 0,
        currency: lead.currency || '',
        quotation_id: lead.quotation_id || '',
        po_number: lead.po_number || '',
        lost_reason_text: lead.lost_reason_text || '',
        _lead: lead,
        ...extra
    };
}

