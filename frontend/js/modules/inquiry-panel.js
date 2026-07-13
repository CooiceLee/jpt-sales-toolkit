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
        // Load lead and related panel data in parallel
        const [lead, activities, preSalesTasks, afterSalesTasks, attachments] = await Promise.all([
            ApiClient.getLead(leadId),
            ApiClient.listActivities(leadId).catch(() => []),
            ApiClient.listPreSalesTasks({ lead_id: leadId, include_archived: true }).catch(() => []),
            ApiClient.listAfterSalesTasks({ lead_id: leadId }).catch(() => []),
            ApiClient.listAttachments(leadId).catch(() => [])
        ]);

        // Parse payload_json from activities
        const parsePayload = (a) => {
            try {
                return a.payload_json ? JSON.parse(a.payload_json) : {};
            } catch { return {}; }
        };

        // Map activities to follow_ups format
        const followUps = activities
            .filter(a => a.action_type === 'follow_up')
            .map(a => {
                const payload = parsePayload(a);
                return {
                    id: a.id,
                    method: payload.method || 'Follow-up',
                    content: payload.content || a.summary || '',
                    date: a.created_at,
                    response_date: payload.response_date || null,
                    customer_feedback: payload.customer_feedback || '',
                    next_action: payload.next_action || '',
                    next_action_date: payload.next_action_date || null,
                    status: payload.status || 'completed',
                    actor_name: a.actor_name || ''
                };
            });

        // Map after-sales tasks to legacy format
        const afterSales = afterSalesTasks.map(t => ({
            id: t.id,
            issue_type: t.issue_type || 'Technical',
            issue_description: t.issue_description || t.summary || '',
            issue_date: t.created_at,
            status: t.status || 'Open',
            technician: t.assignee_name || '',
            solution: t.solution || '',
            row_version: t.row_version
        }));

        // Map lead to legacy inquiry format for panel compatibility
        State.currentInquiry = {
            id: lead.id,
            inquiry_id: lead.display_id,
            company_name: lead.customer?.display_name || '',
            contact_name: lead.customer?.contacts?.[0]?.name || '',
            email: lead.customer?.contacts?.[0]?.email || '',
            phone: lead.customer?.contacts?.[0]?.phone || '',
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

        // Set title
        setText('panel-title', lead.display_id || leadId);

        // Render tabs using the module context that opened the card.
        renderPanelTabs(panelTabForContext(targetContext));

        // Show panel
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
    const tabs = [
        { id: 'basic', label: 'Basic' },
        { id: 'customer', label: 'Customer' },
        { id: 'requirement', label: 'Requirement' },
        { id: 'evaluation', label: 'Evaluation' },
        { id: 'sample', label: 'Sample' },
        { id: 'deal', label: 'Deal' },
        { id: 'fulfillment', label: 'Fulfillment' },
        { id: 'followup', label: 'Follow-ups' },
        { id: 'aftersales', label: 'After-sales' },
        { id: 'files', label: 'Files' }
    ];
    const validActiveTab = tabs.some(t => t.id === activeTabId) ? activeTabId : 'basic';

    const tabsContainer = document.getElementById('panel-tabs');
    togglePanelSaveButton(validActiveTab);
    tabsContainer.innerHTML = tabs.map(t =>
        `<button type="button" class="panel-tab ${t.id === validActiveTab ? 'active' : ''}" data-tab="${t.id}">${t.label}</button>`
    ).join('');

    // Add click handlers
    tabsContainer.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            tabsContainer.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            togglePanelSaveButton(tab.dataset.tab);
            renderPanelContent(tab.dataset.tab);
        });
    });

    // Render context tab
    renderPanelContent(validActiveTab);
}

function togglePanelSaveButton(tabId) {
    const actionTabs = ['sample', 'followup', 'aftersales', 'files'];
    document.getElementById('panel-save-btn')?.classList.toggle('hidden', actionTabs.includes(tabId));
}

