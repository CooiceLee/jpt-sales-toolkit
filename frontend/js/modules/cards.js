(function () {
    'use strict';

    const tr = (text, params) => window.I18n?.t(text, params) || text;

    function emptyState(copy = {}) {
        const title = copy.title || 'No records found';
        const text = copy.text || 'Try adjusting your filters or create a new inquiry.';
        return `
            <div class="empty-state">
                <div class="empty-state-icon">&#128466;</div>
                <div class="empty-state-title">${escapeHtml(tr(title, copy.params))}</div>
                <div class="empty-state-text">${escapeHtml(tr(text, copy.params))}</div>
            </div>
        `;
    }

    function bindCardActions(container) {
        container.querySelectorAll('[data-inquiry-card]').forEach(card => {
            const activate = () => {
                openInquiryPanel(card.dataset.inquiryId, card.dataset.cardContext);
            };
            card.addEventListener('click', activate);
            card.addEventListener('keydown', event => {
                if (!['Enter', ' '].includes(event.key)) return;
                event.preventDefault();
                activate();
            });
        });
        WorklistUI.syncCards(container);
    }

    function renderCards(containerId, inquiries, type = 'handler', emptyCopy = null) {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (!inquiries.length) {
            container.innerHTML = emptyState(emptyCopy || {});
            return;
        }
        container.innerHTML = inquiries.map(item => window.renderInquiryCard(item, type)).join('');
        bindCardActions(container);
    }

    window.renderCards = renderCards;
})();
