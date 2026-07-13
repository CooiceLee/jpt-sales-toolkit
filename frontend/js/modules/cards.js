(function () {
    'use strict';

    const EMPTY_STATE = `
        <div class="empty-state">
            <div class="empty-state-icon">&#128466;</div>
            <div class="empty-state-title">No records found</div>
            <div class="empty-state-text">Try adjusting your filters or create a new inquiry.</div>
        </div>
    `;

    function bindCardActions(container) {
        container.querySelectorAll('[data-inquiry-card]').forEach(card => {
            card.addEventListener('click', () => {
                openInquiryPanel(card.dataset.inquiryId, card.dataset.cardContext);
            });
        });
    }

    function renderCards(containerId, inquiries, type = 'handler') {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (!inquiries.length) {
            container.innerHTML = EMPTY_STATE;
            return;
        }
        container.innerHTML = inquiries.map(item => window.renderInquiryCard(item, type)).join('');
        bindCardActions(container);
    }

    window.renderCards = renderCards;
})();
