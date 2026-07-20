(function () {
    'use strict';
    const tr = text => window.I18n?.t(text) || text;
    let previewSequence = 0;

    function payload() {
        const source = State.customerMerge.source;
        const target = State.customerMerge.target;
        if (!source || !target) return null;
        return {
            source_customer_id: source.id,
            target_customer_id: target.id,
            source_row_version: source.row_version,
            target_row_version: target.row_version,
        };
    }

    function key(value = payload()) {
        return value
            ? [value.source_customer_id, value.source_row_version,
                value.target_customer_id, value.target_row_version].join(':')
            : '';
    }

    function setConfirm(enabled, label) {
        const button = document.getElementById('customer-merge-confirm');
        if (!button) return;
        button.disabled = !enabled;
        button.textContent = tr(label);
    }

    function message(text, error = false) {
        const target = document.getElementById('customer-merge-preview');
        if (target) {
            target.innerHTML = `<div class="empty-state compact${error ? ' error-state' : ''}">${escapeHtml(tr(text))}</div>`;
        }
    }

    function reset(text = 'Select both customers to run a safe merge preview.') {
        previewSequence += 1;
        State.customerMerge.preview = null;
        setConfirm(false, 'Select two customers');
        message(text);
    }

    function render(preview) {
        const counts = preview.counts || {};
        const conflicts = ['field', 'contact', 'domain', 'alias']
            .reduce((sum, type) => sum + (preview[`${type}_conflicts`] || []).length, 0);
        document.getElementById('customer-merge-preview').innerHTML = `<div class="governance-report customer-merge-preview-ready">
            <h4>${escapeHtml(tr('Merge preview ready'))}</h4><p>${escapeHtml(tr('The source will be archived. The target remains active and keeps conflicting values.'))}</p>
            <div class="governance-kpis"><span>${escapeHtml(tr('Leads'))} <strong>${counts.leads || 0}</strong></span>
            <span>${escapeHtml(tr('Contacts'))} <strong>${counts.contacts || 0}</strong></span>
            <span>${escapeHtml(tr('Aliases'))} <strong>${counts.aliases || 0}</strong></span>
            <span>${escapeHtml(tr('Conflicts'))} <strong>${conflicts}</strong></span></div>
            ${CustomerMergeConflictView.render(preview)}</div>`;
    }

    async function run() {
        const request = payload();
        if (!request) return reset();
        if (request.source_customer_id === request.target_customer_id) {
            reset('Source and target must be different customers.');
            return false;
        }
        const sequence = ++previewSequence;
        setConfirm(false, 'Checking merge safety...');
        message('Checking related records and conflicts...');
        try {
            const data = await ApiClient.previewCustomerMerge(request);
            if (sequence !== previewSequence || key(request) !== key()) return false;
            State.customerMerge.preview = { key: key(request), data };
            render(data);
            setConfirm(true, 'Confirm merge');
            return true;
        } catch (error) {
            if (sequence !== previewSequence) return false;
            State.customerMerge.preview = null;
            setConfirm(false, 'Preview required');
            message(error.message || 'Merge preview failed', true);
            return false;
        }
    }

    window.previewSelectedMergeCustomers = run;
    window.CustomerMergePreview = {
        payload, reset, run,
        matches: () => State.customerMerge.preview?.key === key(),
    };
})();
