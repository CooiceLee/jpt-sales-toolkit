(() => {
    function customerIdLiteral(item) {
        return escapeHtml(JSON.stringify(String(item.customer_id || item.id || '')));
    }

    function row(item) {
        const location = [item.city, item.country].filter(Boolean).join(', ');
        const coordinates = item.hasCoordinates
            ? `${Number(item.lat).toFixed(4)}, ${Number(item.lng).toFixed(4)}`
            : '<span style="color:var(--ink-400);">—</span>';
        const action = item.can_edit ? `
            <button type="button" class="btn btn-secondary btn-sm"
                onclick="openCoordinateCorrectionFromReview(${customerIdLiteral(item)})">
                ${escapeHtml(coordinateText(item.status === 'missing' ? 'Add' : 'Fix'))}
            </button>` : '<span aria-hidden="true">—</span>';
        return `
            <tr>
                <td>
                    <div style="font-weight:500;">${escapeHtml(item.customer_name || item.name)}</div>
                    ${item.region ? `<div style="font-size:12px;color:var(--ink-500);">${escapeHtml(item.region)}</div>` : ''}
                </td>
                <td>
                    <div>${escapeHtml(location)}</div>
                    ${item.postal_code ? `<div style="font-size:12px;color:var(--ink-500);">${escapeHtml(item.postal_code)}</div>` : ''}
                    ${item.address ? `<div style="font-size:12px;color:var(--ink-500);">${escapeHtml(item.address)}</div>` : ''}
                </td>
                <td><span class="coord-status-badge status-${escapeHtml(item.status)}">${escapeHtml(item.statusLabel)}</span></td>
                <td style="text-align:center;">${escapeHtml(Number(item.lead_count) || 0)}</td>
                <td style="font-family:var(--mono-font);font-size:12px;">${coordinates}</td>
                <td>${action}</td>
            </tr>`;
    }

    function table(items) {
        return `
            <table class="data-table">
                <thead><tr>
                    <th>${escapeHtml(coordinateText('Customer'))}</th>
                    <th>${escapeHtml(coordinateText('Location'))}</th>
                    <th>${escapeHtml(coordinateText('Status'))}</th>
                    <th style="text-align:center;">${escapeHtml(coordinateText('Leads'))}</th>
                    <th>${escapeHtml(coordinateText('Coordinates'))}</th>
                    <th style="width:120px;">${escapeHtml(coordinateText('Actions'))}</th>
                </tr></thead>
                <tbody>${items.map(row).join('')}</tbody>
            </table>`;
    }

    function pagination({ page, totalPages, shownFrom, shownTo, total }) {
        const summary = coordinateText('Showing {from}–{to} of {total}', {
            from: shownFrom, to: shownTo, total
        });
        return `
            <div class="trip-pagination" aria-label="${escapeHtml(coordinateText('Coordinate review pages'))}">
                <span>${escapeHtml(summary)}</span>
                <span>
                    <button type="button" class="btn btn-secondary btn-sm"
                        onclick="changeCoordinateReviewPage(-1)" ${page <= 1 ? 'disabled' : ''}>${escapeHtml(coordinateText('Previous'))}</button>
                    <span style="padding:0 8px;">${page} / ${totalPages}</span>
                    <button type="button" class="btn btn-secondary btn-sm"
                        onclick="changeCoordinateReviewPage(1)" ${page >= totalPages ? 'disabled' : ''}>${escapeHtml(coordinateText('Next'))}</button>
                </span>
            </div>`;
    }

    window.CoordinateReviewTable = Object.freeze({ table, pagination });
})();
