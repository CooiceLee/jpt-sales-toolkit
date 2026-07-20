(function () {
    'use strict';
    const tr = (text, params = {}) => window.I18n?.t(text, params) || text;

    function renderMergeResult(result) {
        const target = document.getElementById('customer-merge-result');
        if (!target) return;
        target.innerHTML = `<div class="governance-report customer-merge-complete">
            <h4>${escapeHtml(tr('Merge complete'))}</h4>
            <div class="governance-kpis">
                <span>${escapeHtml(tr('Leads moved'))}: <strong>${result.moved_leads || 0}</strong></span>
                <span>${escapeHtml(tr('Contacts moved'))}: <strong>${result.moved_contacts || 0}</strong></span>
                <span>${escapeHtml(tr('Aliases moved'))}: <strong>${result.moved_aliases || 0}</strong></span>
                <span>${escapeHtml(tr('Domains moved'))}: <strong>${result.moved_domains || 0}</strong></span>
            </div>
        </div>`;
    }

    async function refreshAfterMerge() {
        State.inquiries = [];
        const jobs = [refreshAllCounts()];
        if (State.currentInquiry?.id && typeof refreshCurrentInquiryData === 'function') {
            jobs.push(refreshCurrentInquiryData(State.currentInquiry.id));
        }
        await Promise.allSettled(jobs);
    }

    window.mergeSelectedCustomers = async function() {
        if (State.user?.role !== 'leader') return;
        const source = State.customerMerge.source;
        const target = State.customerMerge.target;
        const resultEl = document.getElementById('customer-merge-result');
        if (!source || !target) {
            resultEl.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(tr('Select both source and target customers.'))}</div>`;
            return;
        }
        if (!CustomerMergePreview.matches()) {
            resultEl.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(tr('Run a successful preview before merging.'))}</div>`;
            await previewSelectedMergeCustomers();
            return;
        }
        const question = tr(
            'Merge "{source}" into "{target}"? The source customer will be archived.',
            { source: source.display_name, target: target.display_name }
        );
        if (!confirm(question)) return;

        const button = document.getElementById('customer-merge-confirm');
        try {
            button.disabled = true;
            button.textContent = tr('Merging...');
            const result = await ApiClient.mergeCustomers(CustomerMergePreview.payload());
            CustomerMergeView.clear();
            renderMergeResult(result);
            await refreshAfterMerge();
            notify(tr('Customers merged'));
        } catch (error) {
            console.error('Customer merge error:', error);
            resultEl.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(error.message || tr('Merge failed'))}</div>`;
            if (error.name === 'ConflictError') {
                try {
                    [State.customerMerge.source, State.customerMerge.target] = await Promise.all([
                        ApiClient.getCustomer(source.id),
                        ApiClient.getCustomer(target.id),
                    ]);
                    renderSelectedMergeCustomers();
                } catch (refreshError) {
                    console.error('Customer merge conflict refresh error:', refreshError);
                }
            }
            await previewSelectedMergeCustomers();
        }
    };
})();
