// ===== Detail Panel =====
function panelTabForContext(context) {
    const tabMap = {
        handler: 'basic',
        followup: 'followup',
        sampling: 'sample',
        deal: 'deal',
        fulfillment: 'fulfillment',
        aftersales: 'aftersales',
        customer: 'customer',
        files: 'files',
    };
    return tabMap[context] || 'basic';
}

window.openInquiryPanel = async function(leadId, targetContext = null) {
    try {
        const taskOnly = RoleCapabilities.isTech();
        const [lead, activities, preSalesTasks, afterSalesTasks, attachments] = await Promise.all([
            ApiClient.getLead(leadId),
            taskOnly ? [] : ApiClient.listActivities(leadId).catch(() => []),
            ApiClient.listPreSalesTasks({ lead_id: leadId, include_archived: true }).catch(() => []),
            ApiClient.listAfterSalesTasks({ lead_id: leadId }).catch(() => []),
            taskOnly ? [] : ApiClient.listAttachments(leadId).catch(() => [])
        ]);

        const followUps = activities
            .filter(a => a.action_type === 'follow_up')
            .map(mapFollowUpActivity);
        const afterSales = afterSalesTasks.map(mapAfterSalesTask);

        const primaryContact = getLeadPrimaryContact(lead);

        State.currentInquiry = {
            id: lead.id,
            inquiry_id: lead.display_id,
            company_name: lead.customer?.display_name || '',
            contact_name: primaryContact?.name || '',
            email: primaryContact?.email || '',
            phone: primaryContact?.phone || '',
            country: lead.customer?.country || '',
            city: lead.customer?.city || '',
            stage: lead.sales_stage,
            product: lead.product_category,
            title: lead.title,
            created_at: lead.created_at,
            row_version: lead.row_version,
            follow_ups: followUps,
            after_sales: afterSales,
            sample_tasks: preSalesTasks.map(task => SamplingModule.toView(task)),
            attachments: attachments,
            _lead: lead,
            _customer: lead.customer,
            _activities: activities,
            _preSalesTasks: preSalesTasks,
            _afterSalesTasks: afterSalesTasks,
            _attachments: attachments
        };

        setText('panel-title', lead.display_id || leadId);
        renderPanelTabs(panelTabForContext(targetContext));
        document.getElementById('detail-panel').classList.add('open');
        document.getElementById('app')?.classList.add('detail-open');
    } catch (err) {
        console.error('Panel error:', err);
        alert('Error loading lead');
    }
};

window.closePanel = function() {
    document.getElementById('detail-panel').classList.remove('open');
    document.getElementById('app')?.classList.remove('detail-open');
    State.currentInquiry = null;
};

function renderPanelTabs(activeTabId = 'basic') {
    const allTabs = [
        { id: 'basic', label: 'Basic' },
        { id: 'customer', label: 'Customer' },
        { id: 'requirement', label: 'Requirement' },
        { id: 'evaluation', label: 'Evaluation' },
        { id: 'sample', label: 'Sample' },
        { id: 'deal', label: 'Deal' },
        { id: 'fulfillment', label: 'Fulfillment' },
        { id: 'followup', label: 'Follow-ups' },
        { id: 'aftersales', label: 'After-sales' },
        { id: 'quality', label: 'Data Quality' },
        { id: 'files', label: 'Files' }
    ];
    const lead = State.currentInquiry?._lead;
    const qualityVisible = State.user?.role === 'leader' || lead?.owner_id === State.user?.id
        || (lead?.assignments || []).some(item =>
            item.user_id === State.user?.id && item.assignment_type === 'collaborator');
    const tabs = RoleCapabilities.isTech()
        ? allTabs.filter(tab => ['sample', 'aftersales'].includes(tab.id))
        : allTabs.filter(tab => tab.id !== 'quality' || qualityVisible);
    const validActiveTab = tabs.some(t => t.id === activeTabId) ? activeTabId : 'basic';

    const tabsContainer = document.getElementById('panel-tabs');
    togglePanelSaveButton(validActiveTab);
    tabsContainer.innerHTML = tabs.map(t =>
        `<button type="button" class="panel-tab ${t.id === validActiveTab ? 'active' : ''}" data-tab="${t.id}">${t.label}</button>`
    ).join('');

    tabsContainer.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            tabsContainer.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            togglePanelSaveButton(tab.dataset.tab);
            renderPanelContent(tab.dataset.tab);
        });
    });

    renderPanelContent(validActiveTab);
}

function togglePanelSaveButton(tabId) {
    const actionTabs = ['sample', 'followup', 'aftersales', 'quality', 'files'];
    document.getElementById('panel-save-btn')?.classList.toggle('hidden', actionTabs.includes(tabId));
}
