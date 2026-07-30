// ===== Detail Panel =====
const panelTr = (text, params) => window.I18n?.t(text, params) || text;
let inquiryPanelRequestId = 0;

function resetInquirySaveButton() {
    const button = document.getElementById('panel-save-btn');
    if (!button) return;
    button.disabled = false;
    delete button.dataset.inquirySaveEpoch;
}

function captureInquiryPanelSession() {
    return Object.freeze({
        leadId: State.currentInquiry?.id || null,
        generation: inquiryPanelRequestId
    });
}

function isInquiryPanelSessionCurrent(session) {
    return !!session?.leadId
        && inquiryPanelRequestId === session.generation
        && State.currentInquiry?.id === session.leadId
        && document.getElementById('detail-panel')?.classList.contains('open');
}

window.InquiryPanelSession = Object.freeze({
    capture: captureInquiryPanelSession,
    isCurrent: isInquiryPanelSessionCurrent
});

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
    const panel = document.getElementById('detail-panel');
    if (panel.classList.contains('open') && State.currentInquiry?.id === leadId) {
        document.querySelector(`.panel-tab[data-tab="${panelTabForContext(targetContext)}"]`)?.click();
        return;
    }
    if (!PanelDirtyState.confirmDiscard()) return;
    const requestId = ++inquiryPanelRequestId;
    resetInquirySaveButton();
    State.currentInquiry = null;
    WorklistUI.select(leadId, targetContext);
    setText('panel-title', panelTr('Loading lead...'));
    document.getElementById('panel-tabs').innerHTML = '';
    document.getElementById('panel-content').innerHTML = `<div class="loading-state">${escapeHtml(panelTr('Loading lead details...'))}</div>`;
    document.getElementById('panel-save-btn')?.classList.add('hidden');
    panel.classList.add('open');
    document.getElementById('app')?.classList.add('detail-open');
    try {
        const inquiry = await InquiryPanelData.load(leadId);
        if (requestId !== inquiryPanelRequestId) return;
        State.currentInquiry = inquiry;
        setText('panel-title', [inquiry.inquiry_id || leadId, inquiry.company_name].filter(Boolean).join(' · '));
        renderPanelTabs(panelTabForContext(targetContext));
    } catch (err) {
        if (requestId !== inquiryPanelRequestId) return;
        console.error('Panel error:', err);
        document.getElementById('panel-content').innerHTML = `<div class="empty-state compact error-state">
            <strong>${escapeHtml(panelTr('Unable to load lead details'))}</strong>
            <span>${escapeHtml(err.message || panelTr('Please retry.'))}</span>
            <button type="button" class="btn btn-secondary" data-panel-retry>${escapeHtml(panelTr('Retry'))}</button>
        </div>`;
        document.querySelector('[data-panel-retry]')?.addEventListener('click', () => openInquiryPanel(leadId, targetContext));
    }
};

window.closePanel = function() {
    const panel = document.getElementById('detail-panel');
    if (panel.classList.contains('open') && !PanelDirtyState.confirmDiscard()) return false;
    inquiryPanelRequestId += 1;
    resetInquirySaveButton();
    panel.classList.remove('open');
    document.getElementById('app')?.classList.remove('detail-open');
    State.currentInquiry = null;
    WorklistUI.clear();
    PanelDirtyState.reset();
    return true;
};

function renderPanelTabs(activeTabId = 'basic') {
    const allTabs = [
        { id: 'basic', label: 'Basic' },
        { id: 'customer', label: 'Customer' },
        { id: 'requirement', label: 'Requirement' },
        { id: 'evaluation', label: 'Evaluation' },
        { id: 'sample', label: 'Pre-sales / Sample' },
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
    const qualityCount = Number(lead?.quality_issue_count) || 0;
    tabsContainer.innerHTML = tabs.map(t => {
        const badge = t.id === 'quality'
            ? `<span class="panel-tab-badge ${qualityCount ? '' : 'hidden'}" data-quality-tab-badge
                aria-label="${escapeHtml(panelTr('{count} imported fields require review', { count: qualityCount }))}">${qualityCount}</span>`
            : '';
        return `<button type="button" class="panel-tab ${t.id === validActiveTab ? 'active' : ''}" data-tab="${t.id}"><span>${escapeHtml(panelTr(t.label))}</span>${badge}</button>`;
    }).join('');

    tabsContainer.querySelectorAll('.panel-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            if (tab.classList.contains('active') || !PanelDirtyState.confirmDiscard()) return;
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
