/**
 * Shared render helpers for low-risk vanilla JS modules.
 */
(function() {
    function escape(value) {
        if (typeof escapeHtml === 'function') return escapeHtml(value);
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    window.JPTRender = {
        escape,
        empty(text) {
            return `<div class="empty-state compact">${escape(text)}</div>`;
        },
        field(label, value) {
            return `<div class="visit-info-item"><span>${escape(label)}</span><strong>${escape(value || '-')}</strong></div>`;
        }
    };
})();
