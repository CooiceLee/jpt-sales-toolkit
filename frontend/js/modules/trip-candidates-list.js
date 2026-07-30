async function handleTripError(err, action) {
    if (err?.name === 'ConflictError') {
        alert(I18n.t('{action} conflict: this plan was updated elsewhere. The latest data will be loaded; please retry.', {
            action: I18n.t(action)
        }));
        await loadTripPlanner();
        return;
    }
    alert(I18n.t('Error {action}: {error}', {
        action: I18n.t(action),
        error: I18n.t(err.message || 'Unknown error')
    }));
}

function renderTripCandidates() {
    const container = document.getElementById('trip-candidate-list');
    const candidates = State.tripCandidates || [];
    const pagination = State.tripCandidatePagination || {};
    if (!container) return;
    if (!candidates.length) {
        container.innerHTML = '<div class="empty-state compact">No candidates match current filters</div>';
        return;
    }
    container.innerHTML = `
        <table class="data-table compact-table">
            <thead>
                <tr>
                    <th>Customer</th>
                    <th>Location</th>
                    <th>Score</th>
                    <th>Open</th>
                    <th>Value</th>
                    <th>Reasons</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${candidates.map((item, index) => `
                    <tr>
                        <td>
                            <div style="font-weight:600;">${escapeHtml(item.customer_name)}</div>
                            <div style="font-size:12px;color:var(--ink-500);">${escapeHtml(item.primary_lead_display_id || '')}</div>
                        </td>
                        <td>${escapeHtml([item.city, item.country].filter(Boolean).join(', ') || '-')}</td>
                        <td><span class="score-pill">${escapeHtml(item.score)}</span></td>
                        <td>${item.open_count || 0}</td>
                        <td>${escapeHtml(formatMoney(item.pipeline_value || item.won_value || 0))}</td>
                        <td>${escapeHtml((item.reasons || []).join(', ') || '-')}</td>
                        <td>
                            <button type="button" class="btn btn-secondary btn-sm" onclick="focusTripCandidate(${index})">Map</button>
                            <button type="button" class="btn btn-primary btn-sm" onclick="addCandidateToCurrentPlan(${index})">Add</button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        <div class="trip-pagination">
            <span>Showing ${candidates.length} of ${pagination.total || candidates.length}</span>
            <button type="button" class="btn btn-secondary btn-sm" onclick="loadMoreTripCandidates()" ${pagination.has_more ? '' : 'disabled'}>
                Load more
            </button>
        </div>
    `;
}

window.loadMoreTripCandidates = async function() {
    const pagination = State.tripCandidatePagination || {};
    if (!pagination.has_more) return;
    State.tripCandidatePagination.offset = (pagination.offset || 0) + (pagination.limit || 25);
    await loadTripPlanner({ appendCandidates: true });
};
