function initCustomerMerge() {
    if (State.user?.role !== 'leader') {
        const result = document.getElementById('customer-merge-result');
        if (result) {
            result.innerHTML = '<div class="empty-state compact">Customer merge is available to leader only.</div>';
        }
        return;
    }

    ['source', 'target'].forEach(side => {
        const input = document.getElementById(`merge-${side}-search`);
        if (input && !input.dataset.bound) {
            input.dataset.bound = '1';
            input.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    searchMergeCustomers(side);
                }
            });
        }
    });
    renderSelectedMergeCustomers();
}

window.searchMergeCustomers = async function(side) {
    if (State.user?.role !== 'leader') return;
    const input = document.getElementById(`merge-${side}-search`);
    const query = input?.value?.trim();
    const resultEl = document.getElementById(`merge-${side}-results`);
    if (!resultEl) return;
    if (!query) {
        resultEl.innerHTML = '<div class="empty-state compact">Enter a customer name, country, or city.</div>';
        return;
    }

    try {
        resultEl.innerHTML = '<div class="empty-state compact">Searching...</div>';
        const customers = await ApiClient.listCustomers({ search: query, limit: 12 });
        if (!customers.length) {
            resultEl.innerHTML = '<div class="empty-state compact">No matching customers.</div>';
            return;
        }
        resultEl.innerHTML = customers.map(customer => renderMergeCustomerCard(customer, side)).join('');
    } catch (err) {
        console.error('Customer merge search error:', err);
        resultEl.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(err.message || 'Search failed')}</div>`;
    }
};

function renderMergeCustomerCard(customer, side) {
    const selectedId = State.customerMerge[side]?.id;
    const classes = ['customer-merge-card'];
    if (selectedId === customer.id) classes.push('selected');
    return `
        <button type="button" class="${classes.join(' ')}" onclick="selectMergeCustomer('${side}', '${customer.id}')">
            <strong>${escapeHtml(customer.display_name || '-')}</strong>
            <span>${escapeHtml([customer.country, customer.city].filter(Boolean).join(', ') || 'No location')}</span>
            <span>ID: ${escapeHtml(customer.id)}</span>
        </button>
    `;
}

window.selectMergeCustomer = async function(side, customerId) {
    try {
        const customer = await ApiClient.getCustomer(customerId);
        State.customerMerge[side] = customer;
        renderSelectedMergeCustomers();
        const results = document.getElementById(`merge-${side}-results`);
        if (results) {
            results.querySelectorAll('.customer-merge-card').forEach(card => card.classList.remove('selected'));
        }
        await searchMergeCustomers(side);
    } catch (err) {
        console.error('Select merge customer error:', err);
        alert('Error loading customer: ' + (err.message || 'Unknown error'));
    }
};

function renderSelectedMergeCustomers() {
    ['source', 'target'].forEach(side => {
        const container = document.getElementById(`merge-${side}-selected`);
        if (!container) return;
        const customer = State.customerMerge[side];
        if (!customer) {
            container.innerHTML = '<div class="empty-state compact">No customer selected.</div>';
            return;
        }
        container.innerHTML = `
            <div class="customer-merge-card selected">
                <strong>${escapeHtml(customer.display_name || '-')}</strong>
                <span>${escapeHtml([customer.country, customer.city].filter(Boolean).join(', ') || 'No location')}</span>
                <span>Contacts: ${(customer.contacts || []).length} · Version: ${customer.row_version || 1}</span>
            </div>
        `;
    });
}

