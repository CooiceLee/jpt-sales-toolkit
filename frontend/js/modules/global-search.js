/** Permission-filtered global lead search with keyboard navigation. */
(function () {
    'use strict';
    const tr = (text, params) => window.I18n?.t(text, params) || text;
    let results = [];
    let activeIndex = -1;
    let requestId = 0;

    const input = () => document.getElementById('global-search');
    const popup = () => document.getElementById('global-search-results');
    const status = () => document.getElementById('global-search-status');
    const optionId = index => `global-search-option-${index}`;

    function setStatus(message, error = false) {
        const node = status();
        if (!node) return;
        node.textContent = tr(message);
        node.classList.toggle('error-state', error);
    }

    function open() {
        popup()?.classList.remove('hidden');
        input()?.setAttribute('aria-expanded', 'true');
    }

    function close() {
        popup()?.classList.add('hidden');
        input()?.setAttribute('aria-expanded', 'false');
        input()?.removeAttribute('aria-activedescendant');
        activeIndex = -1;
    }

    function moveActive(direction) {
        if (!results.length) return;
        const next = activeIndex < 0
            ? (direction > 0 ? 0 : results.length - 1)
            : activeIndex + direction;
        activeIndex = (next + results.length) % results.length;
        popup().querySelectorAll('[role="option"]').forEach((option, index) => {
            const active = index === activeIndex;
            option.classList.toggle('active', active);
            option.setAttribute('aria-selected', String(active));
        });
        input().setAttribute('aria-activedescendant', optionId(activeIndex));
        document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: 'nearest' });
    }

    async function choose(index) {
        const lead = results[index];
        if (!lead) return;
        if (window.PanelDirtyState?.confirmDiscard && !window.PanelDirtyState.confirmDiscard()) return;
        input().value = '';
        close();
        await jumpToCustomerStageCards(lead.id, lead.sales_stage, lead.customer_id);
    }

    function render(items) {
        results = items;
        activeIndex = -1;
        const list = document.getElementById('global-search-list');
        list.innerHTML = items.map((lead, index) => {
            const company = lead.customer?.display_name || tr('Unknown Company');
            const location = [lead.customer?.city, lead.customer?.country].filter(Boolean).join(' · ');
            return `<button type="button" class="global-search-option" role="option"
                id="${optionId(index)}" data-global-search-index="${index}" aria-selected="false">
                <span><strong>${escapeHtml(lead.display_id || lead.id)}</strong>${escapeHtml(company)}</span>
                <small>${escapeHtml([location, tr(lead.sales_stage || 'New')].filter(Boolean).join(' · '))}</small>
            </button>`;
        }).join('');
        list.querySelectorAll('[data-global-search-index]').forEach(option => {
            option.addEventListener('click', () => choose(Number(option.dataset.globalSearchIndex)));
        });
        setStatus(items.length ? tr('{count} matching leads', { count: items.length }) : 'No matching leads');
    }

    async function search() {
        const query = input()?.value.trim() || '';
        const currentRequest = ++requestId;
        open();
        if (query.length < 2) {
            results = [];
            document.getElementById('global-search-list').innerHTML = '';
            return setStatus('Type at least 2 characters to search accessible leads.');
        }
        setStatus('Searching accessible leads...');
        try {
            const items = await ApiClient.listLeads({ search: query, limit: 20 });
            if (currentRequest === requestId) render(items);
        } catch (error) {
            if (currentRequest !== requestId) return;
            results = [];
            document.getElementById('global-search-list').innerHTML = '';
            setStatus(error.message || 'Lead search failed. Please retry.', true);
        }
    }

    function onKeydown(event) {
        if (event.key === 'Escape') return close();
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            open();
            moveActive(event.key === 'ArrowDown' ? 1 : -1);
        }
        if (event.key === 'Enter' && activeIndex >= 0) {
            event.preventDefault();
            choose(activeIndex);
        }
    }

    function init() {
        const field = input();
        if (!field || field.dataset.bound) return;
        field.dataset.bound = '1';
        field.addEventListener('input', debounce(search, 250));
        field.addEventListener('focus', search);
        field.addEventListener('keydown', onKeydown);
        document.addEventListener('click', event => {
            if (!event.target.closest('.sidebar-search')) close();
        });
    }

    window.initGlobalSearch = init;
})();
