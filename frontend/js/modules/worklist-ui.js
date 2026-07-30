/** Shared selected-card and data-quality badge state for every worklist. */
(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;
    const selectorId = id => CSS.escape(String(id || ''));

    function syncCards(root = document) {
        const selectedId = String(State.selectedLeadId || '');
        root.querySelectorAll('[data-inquiry-card]').forEach(card => {
            const active = Boolean(selectedId) && card.dataset.inquiryId === selectedId;
            card.classList.toggle('active', active);
            card.setAttribute('aria-pressed', String(active));
        });
    }

    function select(leadId, context = '') {
        State.selectedLeadId = String(leadId || '');
        State.selectedCardContext = context || '';
        syncCards(document);
    }

    function clear() {
        State.selectedLeadId = '';
        State.selectedCardContext = '';
        syncCards(document);
    }

    function updateBadge(badge, count, compact = false) {
        badge.textContent = compact ? String(count) : tr('{count} to review', { count });
        badge.classList.toggle('hidden', count === 0);
        badge.setAttribute('aria-label', tr('{count} imported fields require review', { count }));
    }

    function syncQualityCount(leadId, rawCount) {
        const count = Math.max(0, Number(rawCount) || 0);
        const id = selectorId(leadId);
        document.querySelectorAll(`[data-inquiry-id="${id}"] .quality-badge`)
            .forEach(badge => updateBadge(badge, count));
        if (State.currentInquiry?.id !== leadId) return;
        if (State.currentInquiry._lead) State.currentInquiry._lead.quality_issue_count = count;
        document.querySelectorAll('[data-quality-tab-badge]')
            .forEach(badge => updateBadge(badge, count, true));
    }

    window.WorklistUI = { syncCards, select, clear, syncQualityCount };
})();
