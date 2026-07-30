function renderPreflightIssueList(title, items) {
    return `
        <details class="governance-details" open>
            <summary>${escapeHtml(title)} (${items.length})</summary>
            <ul>
                ${items.slice(0, 50).map(item => `<li>${escapeHtml(item)}</li>`).join('')}
            </ul>
        </details>
    `;
}

window.normalizeCountries = async function() {
    const resultDiv = document.getElementById('governance-result');
    resultDiv.innerHTML = '<div class="loading-state">Normalizing countries...</div>';
    try {
        const result = await ApiClient.normalizeCountries();
        resultDiv.innerHTML = `
            <div class="governance-report">
                <h4>Country Normalization Complete</h4>
                <div class="governance-kpis">
                    <span>Updated customers: <strong>${result.updated_customers || 0}</strong></span>
                    <span>Skipped customers: <strong>${result.skipped_customers || 0}</strong></span>
                </div>
            </div>
        `;
        await loadReviewMap();
        if (document.getElementById('module-coordinate-review')?.classList.contains('active')) {
            await loadCoordinateReview();
        }
    } catch (err) {
        console.error('Normalize countries error:', err);
        resultDiv.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(err.message || 'Normalize failed')}</div>`;
    }
};

window.loadCoordinateAudit = async function() {
    const resultDiv = document.getElementById('governance-result');
    resultDiv.innerHTML = '<div class="loading-state">Loading coordinate audit...</div>';
    try {
        const result = await ApiClient.getCoordinateAudit(100);
        const items = result.items || [];
        resultDiv.innerHTML = `
            <div class="governance-report">
                <h4>Recent Coordinate Changes</h4>
                ${items.length ? `
                    <table class="data-table compact-table">
                        <thead><tr><th>Time</th><th>Actor</th><th>Customer</th><th>Before</th><th>After</th></tr></thead>
                        <tbody>
                            ${items.map(item => `
                                <tr>
                                    <td>${escapeHtml(formatDate(item.created_at))}</td>
                                    <td>${escapeHtml(item.actor_name || item.actor_id || '-')}</td>
                                    <td>${escapeHtml(item.entity_id)}</td>
                                    <td>${escapeHtml(formatCoordinateAuditSnapshot(item.before || {}))}</td>
                                    <td>${escapeHtml(formatCoordinateAuditSnapshot(item.after || {}))}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                ` : '<div class="empty-state compact">No coordinate audit records yet</div>'}
            </div>
        `;
    } catch (err) {
        console.error('Coordinate audit error:', err);
        resultDiv.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(err.message || 'Audit load failed')}</div>`;
    }
};

function formatCoordinateAuditSnapshot(value) {
    return [
        value.lat != null && value.lng != null ? `${value.lat}, ${value.lng}` : '',
        value.city,
        value.country,
        value.geocode_source
    ].filter(Boolean).join(' · ') || '-';
}

window.runBatchRepair = async function() {
    const payload = {
        customer_ids: parseGovernanceIds(document.getElementById('gov-customer-ids')?.value),
        lead_ids: parseGovernanceIds(document.getElementById('gov-lead-ids')?.value),
        country: document.getElementById('gov-country')?.value?.trim() || null,
        region: document.getElementById('gov-region')?.value?.trim() || null,
        lat: numericOrNull(document.getElementById('gov-lat')?.value),
        lng: numericOrNull(document.getElementById('gov-lng')?.value),
        owner_id: document.getElementById('gov-owner-id')?.value?.trim() || null,
        product_category: document.getElementById('gov-product')?.value?.trim() || null,
        application: document.getElementById('gov-application')?.value?.trim() || null
    };
    if (!payload.customer_ids.length && !payload.lead_ids.length) {
        alert(I18n.t('Enter at least one Customer ID or Lead ID'));
        return;
    }
    const resultDiv = document.getElementById('governance-result');
    resultDiv.innerHTML = '<div class="loading-state">Running batch repair...</div>';
    try {
        const result = await ApiClient.batchRepair(payload);
        resultDiv.innerHTML = `
            <div class="governance-report">
                <h4>Batch Repair Complete</h4>
                <div class="governance-kpis">
                    <span>Updated customers: <strong>${result.updated_customers || 0}</strong></span>
                    <span>Updated leads: <strong>${result.updated_leads || 0}</strong></span>
                    <span>Errors: <strong>${(result.errors || []).length}</strong></span>
                </div>
                ${(result.errors || []).length ? renderPreflightIssueList('Errors', result.errors) : ''}
            </div>
        `;
        await loadReviewMap();
    } catch (err) {
        console.error('Batch repair error:', err);
        resultDiv.innerHTML = `<div class="empty-state compact error-state">${escapeHtml(err.message || 'Batch repair failed')}</div>`;
    }
};

function parseGovernanceIds(value) {
    return String(value || '')
        .split(/[\n,]+/)
        .map(item => item.trim())
        .filter(Boolean);
}
