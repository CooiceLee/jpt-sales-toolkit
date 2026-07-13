window.mergeSelectedCustomers = async function() {
    if (State.user?.role !== 'leader') return;
    const source = State.customerMerge.source;
    const target = State.customerMerge.target;
    const resultEl = document.getElementById('customer-merge-result');
    if (!source || !target) {
        alert('Select both source and target customers.');
        return;
    }
    if (source.id === target.id) {
        alert('Source and target must be different customers.');
        return;
    }
    if (!confirm(`Merge "${source.display_name}" into "${target.display_name}"? The source customer will be archived.`)) {
        return;
    }

    try {
        const result = await ApiClient.mergeCustomers({
            source_customer_id: source.id,
            target_customer_id: target.id,
            source_row_version: source.row_version,
            target_row_version: target.row_version
        });
        State.customerMerge.source = null;
        State.customerMerge.target = null;
        renderSelectedMergeCustomers();
        if (resultEl) {
            resultEl.innerHTML = `
                <div class="governance-report">
                    <h4>Merge complete</h4>
                    <div class="governance-kpis">
                        <span>Leads moved: ${result.moved_leads}</span>
                        <span>Contacts moved: ${result.moved_contacts}</span>
                        <span>Domains moved: ${result.moved_domains}</span>
                    </div>
                </div>
            `;
        }
        ['source', 'target'].forEach(side => {
            const results = document.getElementById(`merge-${side}-results`);
            if (results) results.innerHTML = '';
            const input = document.getElementById(`merge-${side}-search`);
            if (input) input.value = '';
        });
        notify('Customers merged');
    } catch (err) {
        console.error('Customer merge error:', err);
        if (resultEl) {
            resultEl.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(err.message || 'Merge failed')}</div>`;
        }
    }
};

