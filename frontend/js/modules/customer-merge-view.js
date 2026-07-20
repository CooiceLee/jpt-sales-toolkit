(function () {
    'use strict';
    const tr = (text, params = {}) => window.I18n?.t(text, params) || text;
    const timers = {};
    const searchSequence = { source: 0, target: 0 };
    const selectionSequence = { source: 0, target: 0 };

    window.initCustomerMerge = function() {
        if (State.user?.role !== 'leader') {
            CustomerMergePreview.reset('Customer merge is available to Leader only.');
            return;
        }
        ['source', 'target'].forEach(side => {
            const input = document.getElementById(`merge-${side}-search`);
            if (!input || input.dataset.bound) return;
            input.dataset.bound = '1';
            input.addEventListener('keydown', event => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    searchMergeCustomers(side);
                }
            });
            input.addEventListener('input', () => {
                clearTimeout(timers[side]);
                const query = input.value.trim();
                if (!query) document.getElementById(`merge-${side}-results`).innerHTML = '';
                if (query.length >= 2) timers[side] = setTimeout(() => searchMergeCustomers(side), 250);
            });
        });
        renderSelectedMergeCustomers();
        CustomerMergePreview.reset();
    };

    window.searchMergeCustomers = async function(side) {
        if (State.user?.role !== 'leader' || !['source', 'target'].includes(side)) return;
        const query = document.getElementById(`merge-${side}-search`)?.value?.trim();
        const resultEl = document.getElementById(`merge-${side}-results`);
        if (!resultEl) return;
        if (!query || query.length < 2) {
            resultEl.innerHTML = `<div class="empty-state compact">${escapeHtml(tr('Enter at least two characters.'))}</div>`;
            return;
        }
        const sequence = ++searchSequence[side];
        try {
            resultEl.innerHTML = `<div class="empty-state compact">${escapeHtml(tr('Searching names and aliases...'))}</div>`;
            const customers = await ApiClient.listCustomerMergeCandidates(query, 12);
            if (sequence !== searchSequence[side]
                || document.getElementById(`merge-${side}-search`)?.value?.trim() !== query) return;
            resultEl.innerHTML = customers.length
                ? customers.map(customer => renderMergeCustomerCard(customer, side)).join('')
                : `<div class="empty-state compact">${escapeHtml(tr('No matching customers.'))}</div>`;
        } catch (error) {
            if (sequence !== searchSequence[side]) return;
            console.error('Customer merge search error:', error);
            resultEl.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(error.message || tr('Search failed'))}</div>`;
        }
    };

    function renderMergeCustomerCard(customer, side) {
        const selected = State.customerMerge[side]?.id === customer.id ? ' selected' : '';
        const matchLabel = customer.matched_on === 'alias' ? 'Matched alias' : 'Matched name';
        return `<button type="button" class="customer-merge-card${selected}" onclick="selectMergeCustomer('${side}', '${escapeHtml(customer.id)}')">
            <span class="customer-merge-card-head"><strong>${escapeHtml(customer.display_name || '-')}</strong><b class="score-pill">${customer.score}%</b></span>
            <span>${escapeHtml([customer.country, customer.city].filter(Boolean).join(', ') || tr('No location'))}</span>
            <span>${escapeHtml(tr(matchLabel))}: ${escapeHtml(customer.matched_value || customer.display_name || '-')}</span>
        </button>`;
    }

    window.selectMergeCustomer = async function(side, customerId) {
        const sequence = ++selectionSequence[side];
        try {
            const customer = await ApiClient.getCustomer(customerId);
            if (sequence !== selectionSequence[side]) return;
            State.customerMerge[side] = customer;
            State.customerMerge.preview = null;
            document.getElementById('customer-merge-result').innerHTML = '';
            renderSelectedMergeCustomers();
            await Promise.all([searchMergeCustomers(side), previewSelectedMergeCustomers()]);
        } catch (error) {
            if (sequence !== selectionSequence[side]) return;
            console.error('Select merge customer error:', error);
            document.getElementById('customer-merge-preview').innerHTML =
                `<div class="empty-state compact error-state">${escapeHtml(error.message || tr('Error loading customer'))}</div>`;
        }
    };

    window.renderSelectedMergeCustomers = function() {
        ['source', 'target'].forEach(side => {
            const container = document.getElementById(`merge-${side}-selected`);
            if (!container) return;
            const customer = State.customerMerge[side];
            if (!customer) {
                container.innerHTML = `<div class="empty-state compact">${escapeHtml(tr('No customer selected.'))}</div>`;
                return;
            }
            const aliases = (customer.aliases || []).map(item => item.alias_name).filter(Boolean);
            container.innerHTML = `<div class="customer-merge-card selected"><strong>${escapeHtml(customer.display_name || '-')}</strong>
                <span>${escapeHtml([customer.country, customer.city].filter(Boolean).join(', ') || tr('No location'))}</span>
                ${aliases.length ? `<span>${escapeHtml(tr('Aliases'))}: ${escapeHtml(aliases.slice(0, 3).join(' · '))}</span>` : ''}
                <span>${escapeHtml(tr('Contacts'))}: ${(customer.contacts || []).length} · ${escapeHtml(tr('Version'))}: ${customer.row_version || 1}</span></div>`;
        });
    };

    window.CustomerMergeView = {
        clear() {
            State.customerMerge.source = null;
            State.customerMerge.target = null;
            State.customerMerge.preview = null;
            renderSelectedMergeCustomers();
            CustomerMergePreview.reset();
            ['source', 'target'].forEach(side => {
                searchSequence[side] += 1;
                selectionSequence[side] += 1;
                document.getElementById(`merge-${side}-results`).innerHTML = '';
                document.getElementById(`merge-${side}-search`).value = '';
            });
        },
    };
})();
