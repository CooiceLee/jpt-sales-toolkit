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
        error: TripCandidateState.friendlyError(err)
    }));
}

function inCurrentPlan(candidate) {
    return (State.currentTripPlan?.stops || []).some(
        stop => stop.stop_kind !== 'free' && stop.customer_id === candidate.customer_id
    );
}

function renderTripCandidates() {
    const container = document.getElementById('trip-candidate-list');
    const candidates = State.tripCandidates || [];
    const pagination = State.tripCandidatePagination || {};
    if (!container) return;
    if (!candidates.length) {
        container.innerHTML = `<div class="empty-state compact">${escapeHtml(I18n.t('No candidates match current filters'))}</div>`;
        return;
    }
    container.innerHTML = `
        <table class="data-table compact-table">
            <thead>
                <tr>
                    <th>${escapeHtml(I18n.t('Customer'))}</th>
                    <th>${escapeHtml(I18n.t('Location'))}</th>
                    <th>${escapeHtml(I18n.t('Score'))}</th>
                    <th>${escapeHtml(I18n.t('Open'))}</th>
                    <th>${escapeHtml(I18n.t('Value'))}</th>
                    <th>${escapeHtml(I18n.t('Reasons'))}</th>
                    <th>${escapeHtml(I18n.t('Actions'))}</th>
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
                        <td>${escapeHtml((item.reasons || []).map(reason => I18n.t(reason)).join(', ') || '-')}</td>
                        <td class="trip-candidate-actions">
                            <button type="button" class="btn btn-secondary btn-sm" onclick="focusTripCandidate(${index})">${escapeHtml(I18n.t('Map'))}</button>
                            ${inCurrentPlan(item) ? `
                                <button type="button" class="btn btn-secondary btn-sm" disabled>${escapeHtml(I18n.t('Already added'))}</button>
                            ` : TripCandidateState.hasExactCoordinates(item) ? `
                                <button type="button" class="btn btn-primary btn-sm" onclick="addCandidateToCurrentPlan(${index})">${escapeHtml(I18n.t('Add to plan'))}</button>
                            ` : `
                                <button type="button" class="btn btn-primary btn-sm" disabled title="${escapeHtml(I18n.t('Add precise coordinates before adding this customer.'))}">${escapeHtml(I18n.t('Add to plan'))}</button>
                                <button type="button" class="btn btn-secondary btn-sm" onclick="openTripCandidateCoordinateReview(${index})">${escapeHtml(I18n.t('Coordinate Review'))}</button>
                            `}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        <div class="trip-pagination">
            <span>${escapeHtml(I18n.t('Showing {shown} of {total}', {
                shown: candidates.length,
                total: pagination.total || candidates.length
            }))}</span>
            <button type="button" class="btn btn-secondary btn-sm" onclick="loadMoreTripCandidates()" ${pagination.has_more ? '' : 'disabled'}>
                ${escapeHtml(I18n.t('Load more'))}
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
