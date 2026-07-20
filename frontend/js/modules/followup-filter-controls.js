(function () {
    'use strict';

    function read() {
        return {
            mode: document.getElementById('followup-activity-filter')?.value || 'all',
            from: document.getElementById('followup-activity-from')?.value || '',
            to: document.getElementById('followup-activity-to')?.value || '',
        };
    }

    function syncCustomVisibility() {
        const fields = document.getElementById('followup-custom-dates');
        if (!fields) return;
        const visible = read().mode === 'custom';
        fields.classList.toggle('hidden', !visible);
        fields.setAttribute('aria-hidden', String(!visible));
    }

    function init() {
        const select = document.getElementById('followup-activity-filter');
        if (!select || select.dataset.bound) return;
        select.dataset.bound = '1';
        select.addEventListener('change', () => {
            syncCustomVisibility();
            loadFollowup();
        });
        ['followup-activity-from', 'followup-activity-to'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', loadFollowup);
        });
        syncCustomVisibility();
    }

    window.FollowupFilterControls = { init, read, syncCustomVisibility };
})();
